import json
import socket
import time
import argparse
import os

# Constants
MSS = 1400  # Maximum Segment Size for each packet
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "send_file.txt"
timeout = 1.0  # Initialize timeout to some value but update it as ACK packets arrive

# Used in finding Timeout
estimated_rtt = timeout
dev_rtt = 0.0

# Used in adaptive window size
DESIRED_RATE_BPS = 50_000_000  # 50 Mbps


def send_file(server_ip, server_port, enable_fast_retransmit):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    # Initialize UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    # Wait for client to initiate connection
    client_address = None
    file_path = FILE_PATH  # Predefined file name

    # Calculate initial window size
    WINDOW_SIZE = get_window_size()

    with open(file_path, 'rb') as file:
        seq_num = 0
        window_base = 0
        unacked_packets = {}
        duplicate_ack_count = {}
        last_ack_received = -1

        count_starts = 0

        while True:
            while seq_num < window_base + WINDOW_SIZE:  # Use window-based sending
                chunk = file.read(MSS)
                if not chunk:
                    # End of file
                    break

                # Create and send the packet
                packet = create_packet(seq_num, chunk)
                if client_address:
                    server_socket.sendto(packet, client_address)
                else:
                    print("Waiting for client connection...")
                    data, client_address = server_socket.recvfrom(1024)
                    print(
                        f"Connection established with client {client_address}")
                    server_socket.sendto(b"START_SYN", client_address)

                ##
                unacked_packets[seq_num] = (
                    packet, time.time())  # Track sent packets
                print(f"Sent packet {seq_num}")
                seq_num += 1

            # Wait for ACKs and retransmit if needed
            try:
                # Handle ACKs, Timeout, Fast retransmit
                global timeout
                server_socket.settimeout(timeout)
                ack_packet, _ = server_socket.recvfrom(1024)
                if ack_packet == b"START":
                    count_starts += 1
                    if count_starts == 3:
                        server_socket.sendto(b"START_SYN", client_address)
                        count_starts = 0
                    continue
                ack_seq_num = get_seq_no_from_ack_pkt(ack_packet)

                if ack_seq_num > last_ack_received:
                    print(f"Received cumulative ACK for packet {ack_seq_num}")
                    last_ack_received = ack_seq_num
                    # Slide the window forward
                    window_base = ack_seq_num

                    # Setting new Timeout value
                    sample_rtt = time.time() - unacked_packets[ack_seq_num][1]
                    timeout = get_timeout(sample_rtt)
                    # Update window size based on new RTT
                    WINDOW_SIZE = max(5, get_window_size())

                    # Remove acknowledged packets from the buffer
                    for unacked_packet_seq_num in list(unacked_packets.keys()):
                        if unacked_packet_seq_num <= ack_seq_num:
                            del unacked_packets[unacked_packet_seq_num]

                    # Reset duplicate ACK counts
                    duplicate_ack_count.clear()

                else:
                    # Duplicate ACK received
                    duplicate_ack_count[ack_seq_num] = duplicate_ack_count.get(
                        ack_seq_num, 0) + 1

                    print(
                        f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count[ack_seq_num]}")

                    if enable_fast_retransmit and duplicate_ack_count[ack_seq_num] >= DUP_ACK_THRESHOLD:
                        print("Entering fast recovery mode")
                        fast_retransmit(
                            server_socket, client_address, unacked_packets)
                        duplicate_ack_count.clear()

            except socket.timeout:
                # Timeout handling: retransmit all unacknowledged packets
                print("Timeout occurred, retransmitting unacknowledged packets")
                retransmit_unacked_packets(
                    server_socket, client_address, unacked_packets)

                # Performing exponential backoff
                timeout *= 2
                timeout = min(timeout, 10.0)

                # Reset duplicate ACK counts after timeout
                duplicate_ack_count.clear()

            # Check if we are done sending the file
            if not chunk and len(unacked_packets) == 0:
                while True:
                    try:
                        server_socket.sendto(b"END", client_address)
                        end_ack, _ = server_socket.recvfrom(1024)
                        if end_ack == b"END_ACK":
                            print("Received END_ACK signal from client")
                            break
                    except socket.timeout:
                        continue
                print("File transfer complete")
                break


def create_packet(seq_num, data):
    """
    Create a packet with the sequence number and data.
    """
    packet = {
        "seq_num": seq_num,
        "data_len": len(data),
        "data": data.decode()
    }
    return json.dumps(packet).encode()


def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _) in unacked_packets.items():
        new_send_time = time.time()
        unacked_packets[seq_num] = (packet, new_send_time)
        server_socket.sendto(packet, client_address)
        print(f"Retransmitted packet with seq_num {seq_num}")


def fast_retransmit(server_socket, client_address, unacked_packets):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    if unacked_packets:
        min_unacked_seq_num = min(unacked_packets.keys())
        packet, _ = unacked_packets[min_unacked_seq_num]
        new_send_time = time.time()
        unacked_packets[min_unacked_seq_num] = (packet, new_send_time)
        server_socket.sendto(packet, client_address)
        print(
            f"Fast recovery: retransmitted packet with seq_num {min_unacked_seq_num}")


def get_seq_no_from_ack_pkt(ack_packet):
    """
    Get sequence number from acknowledgment packet
    """
    seq_num, _ = ack_packet.split(b"|", 1)
    return int(seq_num)


def get_timeout(sample_rtt, alpha=0.125, beta=0.25):
    """
    Get Timeout value
    """
    global estimated_rtt
    global dev_rtt

    estimated_rtt = (1 - alpha) * estimated_rtt + alpha * sample_rtt
    dev_rtt = (1 - beta) * dev_rtt + beta * abs(sample_rtt - estimated_rtt)

    return max(estimated_rtt + 4 * dev_rtt, 1.0)


def get_window_size():
    """
    This method computes a adaptive window size to get a specific throughput
    """
    global MSS
    global DESIRED_RATE_BPS
    global estimated_rtt

    return int((DESIRED_RATE_BPS * estimated_rtt) / 8) // MSS


# Parse command-line arguments
parser = argparse.ArgumentParser(
    description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast_recovery', type=int, help='Enable fast recovery')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, args.fast_recovery)
