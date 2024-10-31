# Simple File Transfer protocol using UDP sockets

Add a dummy text file named "send_file.txt" in the same folder


## P1 Files (implements reliability)

Running server: 
```bash
python3 p1_server.py <SERVER_IP> <SERVER_PORT> <FAST_RECOVERY_BOOL>
```
Running client:
```bash
python3 p1_client.py <SERVER_IP> <SERVER_PORT>
```

## P2 Files (implements reliability and congestion control)

Running server: 
```bash
python3 p2_server.py <SERVER_IP> <SERVER_PORT> <FAST_RECOVERY_BOOL>
```
Running client:
```bash
python3 p2_client.py <SERVER_IP> <SERVER_PORT>
```
