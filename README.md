# Reliable File Transfer using UDP and SDN

A reliable file transfer application built using Python UDP sockets and Software-Defined Networking (SDN). The project implements application-layer reliability and dynamic network path management using an OS-Ken OpenFlow controller and Mininet.

## 1. Project Overview

UDP is a connectionless transport protocol that does not guarantee packet delivery, ordering or retransmission.

This project addresses these limitations by implementing a reliability mechanism at the application layer. It uses sequence numbers, acknowledgements, timeout-based retransmissions, duplicate packet detection and SHA-256 file integrity verification.

The project also integrates an SDN controller to detect network link failures and dynamically switch traffic between primary and backup paths.

## 2. Objectives

- Implement reliable file transfer using UDP sockets.
- Implement packet sequence numbering and acknowledgements.
- Detect missing and duplicate packets.
- Implement timeout-based retransmission.
- Verify received files using SHA-256.
- Create a Mininet network with primary and backup paths.
- Implement dynamic forwarding using OpenFlow 1.3.
- Detect link failures and restore network connectivity.
- Evaluate file transfer performance under different conditions.

## 3. System Architecture

The project contains four major components:

1. **UDP Client:** Reads files, divides them into packets and transmits them.
2. **UDP Server:** Receives packets, sends acknowledgements and reconstructs files.
3. **Reliability Protocol:** Handles sequence numbers, ACKs, retransmissions, duplicate detection and integrity verification.
4. **SDN Controller:** Manages network forwarding rules and selects available paths.

### Network Topology

The Mininet topology consists of two hosts and four OpenFlow switches.

**Primary path:**

`h1 → s1 → s2 → s4 → h2`

**Backup path:**

`h1 → s1 → s3 → s4 → h2`

When the primary path fails, the controller selects the backup path. When the failed link is restored, it reinstalls the primary forwarding path.

## 4. Technologies Used

| Technology | Purpose |
|---|---|
| Python | Client, server and protocol implementation |
| UDP sockets | File transmission |
| Mininet | Network emulation |
| Open vSwitch | Software switches |
| OS-Ken | SDN controller |
| OpenFlow 1.3 | Controller-switch communication |
| SHA-256 | File integrity verification |
| NumPy | Numerical operations |
| Matplotlib | Performance graphs |
| Ubuntu | Development environment |
| VirtualBox | Virtual machine environment |

## 5. Project Structure

```text
Reliable-File-Transfer-using-UDP-and-SDN/
│
├── client/
│   ├── __init__.py
│   └── udp_client.py
│
├── server/
│   ├── __init__.py
│   └── udp_server.py
│
├── protocol/
│   ├── __init__.py
│   └── reliability.py
│
├── controller/
│   ├── __init__.py
│   └── sdn_controller.py
│
├── topology/
│   ├── __init__.py
│   └── topology.py
│
├── test_files/
│   ├── sample.txt
│   └── sample.bin
│
├── received_files/
│
├── logs/
│
├── results/
│   ├── performance_results.csv
│   ├── generate_graphs.py
│   └── graphs/
│
├── screenshots/
│
├── requirements.txt
├── .gitignore
└── README.md
```

Generated received files and large generated test files are excluded from Git using `.gitignore`.

## 6. Prerequisites

- Ubuntu Linux
- Python 3
- Mininet
- Open vSwitch
- OS-Ken
- Git
- Matplotlib
- NumPy

The SDN controller uses a separate Python virtual environment to run OS-Ken.

## 7. Installation

### Step 1: Install system dependencies

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git mininet openvswitch-switch -y
```

### Step 2: Create the OS-Ken virtual environment

```bash
python3 -m venv --system-site-packages ~/osken-venv
source ~/osken-venv/bin/activate
```

### Step 3: Install controller dependencies

```bash
pip install os-ken==3.1.1 eventlet==0.36.1
```

### Step 4: Install project dependencies

From the project directory:

```bash
cd ~/Reliable-File-Transfer-SDN
pip install -r requirements.txt
```

## 8. Running the Project

The system uses three terminals.

### Terminal 1: Start the SDN Controller

```bash
cd ~/Reliable-File-Transfer-SDN

source ~/osken-venv/bin/activate

export PYTHONPATH="$HOME/Reliable-File-Transfer-SDN:$PYTHONPATH"

osken-manager --ofp-tcp-listen-port 6653 controller.sdn_controller
```

The controller connects to the four OpenFlow switches and installs forwarding rules.

### Terminal 2: Start Mininet

```bash
cd ~/Reliable-File-Transfer-SDN

sudo mn -c

sudo python3 topology/topology.py --remote
```

At the Mininet prompt, test connectivity:

```bash
h1 ping -c 5 10.0.0.2
```

### Terminal 3: Start the UDP Server

At the `mininet>` prompt:

```bash
h2 sh -c 'cd /home/pes1ug25am050/Reliable-File-Transfer-SDN && PYTHONPATH=/home/pes1ug25am050/Reliable-File-Transfer-SDN python3 -u -m server.udp_server > logs/server_mininet.log 2>&1 &'
```

### Transfer a File

At the `mininet>` prompt:

```bash
h1 sh -c 'cd /home/pes1ug25am050/Reliable-File-Transfer-SDN && PYTHONPATH=/home/pes1ug25am050/Reliable-File-Transfer-SDN python3 -m client.udp_client test_files/sample.txt --host 10.0.0.2'
```

The client sends the file through the Mininet network. The server reconstructs the file and verifies its integrity.

## 9. SDN Failure and Recovery Demonstration

To monitor connectivity continuously:

```bash
h1 ping 10.0.0.2 > /tmp/phase5_ping.log 2>&1 &
```

Disconnect the primary link at the Mininet prompt:

```bash
link s1 s2 down
```

The controller detects the failure and activates the backup path:

`h1 → s1 → s3 → s4 → h2`

Inspect the backup forwarding rules:

```bash
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh ovs-ofctl -O OpenFlow13 dump-flows s3
sh ovs-ofctl -O OpenFlow13 dump-flows s4
```

Restore the primary link:

```bash
link s1 s2 up
```

The controller detects restoration and reinstalls the primary forwarding path.

Stop the background ping:

```bash
h1 killall ping
```

## 10. Reliability Features

- **Sequence Numbers:** Identify individual data packets.
- **Acknowledgements:** Confirm successful packet reception.
- **Timeouts:** Detect missing acknowledgements.
- **Retransmissions:** Resend packets when acknowledgements are not received.
- **Duplicate Detection:** Prevent duplicate packet storage.
- **SHA-256:** Verify the integrity of the reconstructed file.

The implemented configuration uses a window size of 5 and an acknowledgement timeout of 0.5 seconds.

## 11. Performance Evaluation

The following measurements were recorded during testing.

| File Size | Network Condition | Transfer Time (s) | Throughput (Mbps) | Retransmissions | Integrity |
|---|---|---:|---:|---:|---|
| 5 MB | Normal | 14.532 | 2.886 | 0 | PASSED |
| 20 MB | Normal | 57.655 | 2.910 | 0 | PASSED |
| 50 MB | Normal | 151.616 | 2.766 | 0 | PASSED |
| 50 MB | Link Failure | 405.855 | 1.033 | 36 | PASSED |

### Performance Graphs

The `results/graphs/` directory contains:

- Transfer time comparison
- Throughput comparison
- Retransmission comparison
- Integrity verification results

The measurements show that the 50 MB link-failure test took longer and recorded additional retransmissions compared with the normal 50 MB test.

## 12. File Integrity Verification

The original and received files can be compared using SHA-256:

```bash
sha256sum test_files/failure_test.bin
sha256sum received_files/failure_test_31c50ebd.bin
```

Matching hashes indicate that the original and received file contents are identical.

## 13. Logs and Results

- `logs/` contains server and client execution logs.
- `results/performance_results.csv` contains the measured performance data.
- `results/graphs/` contains generated performance graphs.
- `screenshots/` contains implementation and testing evidence.

## 14. Limitations

- The current implementation is designed around the configured two-host Mininet topology.
- The server handles transfers using its current transfer-state implementation rather than a demonstrated multi-client concurrent server.
- Performance measurements depend on the virtual machine and emulated network conditions.
- Additional congestion and concurrent-client testing can be performed as future enhancements.

## 15. Future Enhancements

- Support multiple simultaneous clients.
- Implement adaptive timeout and window sizing.
- Introduce congestion-aware transmission.
- Add more complex network topologies.
- Develop a graphical interface for monitoring file transfers and network status.

## 16. Conclusion

This project demonstrates reliable file transmission using UDP with application-layer reliability mechanisms and SDN-based network path management.

Sequence numbers, acknowledgements, retransmissions and duplicate detection provide reliable packet handling. SHA-256 verifies the integrity of received files.

The OS-Ken controller manages OpenFlow switches and dynamically selects primary or backup forwarding paths during link failures.

The implementation was evaluated under normal and link-failure conditions using different file sizes, and the results were recorded through CSV data and performance graphs.
