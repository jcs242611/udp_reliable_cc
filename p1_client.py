import json
import socket
import argparse

# Constants
MSS = 1400  # Maximum Segment Size


def receive_file(server_ip, server_port):
    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """
    # Initialize UDP socket

    # Add logic for handling packet loss while establishing connection
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Set timeout for server response

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = "received_file.txt"  # Default file name

    packet_buffer = {}  # Buffer to store out of order packets

    connection_with_server = False

    with open(output_file_path, 'wb') as file:
        while not connection_with_server:
            try:
                # Send initial connection request to server
                client_socket.sendto(b"START", server_address)
                start_syn, _ = client_socket.recvfrom(1024)
                if start_syn == b"START_SYN":
                    connection_with_server = True
            except socket.timeout:
                print("Finding Server...")

        while True:
            try:
                # Receive the packet
                packet, _ = client_socket.recvfrom(
                    MSS + 100)  # Allow room for headers

                # Logic to handle end of file
                if packet == b"END":
                    if len(packet_buffer) != 0:
                        connection_with_server = False
                        continue
                    print("Received END signal from server, file transfer complete.")
                    client_socket.sendto(b"END_ACK", server_address)
                    break
                elif packet == b"START_SYN":
                    continue

                seq_num, data = parse_packet(packet)

                # If the packet is in order, write it to the file
                if seq_num == expected_seq_num:
                    file.write(data)
                    print(f"Received packet {seq_num}, writing to file")

                    # Update expected seq number and send cumulative ACK for the received packet
                    expected_seq_num += 1

                    # Check buffer for out of order packets and write them to file
                    while expected_seq_num in packet_buffer:
                        file.write(packet_buffer.pop(expected_seq_num))
                        print(
                            f"Writing buffered packet {expected_seq_num} to file")
                        expected_seq_num += 1

                    send_ack(client_socket, server_address,
                             expected_seq_num - 1)
                elif seq_num < expected_seq_num:
                    # Duplicate or old packet, send ACK again
                    send_ack(client_socket, server_address,
                             expected_seq_num - 1)
                else:
                    # packet arrived out of order
                    if seq_num not in packet_buffer.keys():
                        packet_buffer[seq_num] = data
                        print(
                            f"Received out of order packet {seq_num}, adding to buffer")
                    send_ack(client_socket, server_address,
                             expected_seq_num - 1)
            except socket.timeout:
                print("Timeout waiting for data")


def parse_packet(packet_in_json):
    """
    Parse the packet to extract the sequence number and data.
    """
    packet = json.loads(packet_in_json.decode())
    return int(packet["seq_num"]), packet["data"].encode()


def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{seq_num}|ACK".encode()
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent cumulative ACK for packet {seq_num}")

    # Parse command-line arguments
parser = argparse.ArgumentParser(
    description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the client
receive_file(args.server_ip, args.server_port)
