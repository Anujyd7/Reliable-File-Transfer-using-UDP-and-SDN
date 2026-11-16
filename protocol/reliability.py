import struct
import hashlib
import json

# ==========================================
# UDP FILE TRANSFER CONFIGURATION
# ==========================================

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

CHUNK_SIZE = 1000
WINDOW_SIZE = 5

ACK_TIMEOUT = 0.5
MAX_RETRIES = 10

MAX_DATAGRAM_SIZE = 65507

# ==========================================
# PACKET TYPES
# ==========================================

START = 1
DATA = 2
ACK = 3
FIN = 4
DONE = 5
ERROR = 6

# Special sequence number for START acknowledgment
START_ACK_SEQ = 0xFFFFFFFF

# ==========================================
# PACKET HEADER
# ==========================================

# Format:
# B  = packet type
# 16s = transfer ID
# I  = sequence number
# I  = total packets

HEADER = struct.Struct("!B16sII")

def create_packet(packet_type, transfer_id,
                  sequence=0, total=0, payload=b""):

    if len(transfer_id) != 16:
        raise ValueError("Transfer ID must contain 16 bytes")

    header = HEADER.pack(
        packet_type,
        transfer_id,
        sequence,
        total
    )

    return header + payload

def decode_packet(packet):

    if len(packet) < HEADER.size:
        raise ValueError("Incomplete packet header")

    packet_type, transfer_id, sequence, total = (
        HEADER.unpack(packet[:HEADER.size])
    )

    payload = packet[HEADER.size:]

    return packet_type, transfer_id, sequence, total, payload

# ==========================================
# FILE INTEGRITY
# ==========================================

def calculate_sha256(data):

    sha = hashlib.sha256()
    sha.update(data)

    return sha.hexdigest()

def calculate_file_sha256(filename):

    sha = hashlib.sha256()

    with open(filename, "rb") as file:

        while True:

            chunk = file.read(4096)

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()

# ==========================================
# METADATA ENCODING
# ==========================================

def encode_metadata(metadata):

    return json.dumps(metadata).encode("utf-8")

def decode_metadata(data):

    return json.loads(data.decode("utf-8"))
