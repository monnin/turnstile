import os
import select
import socket
import struct
import sys

DEF_PEER_IP = "localhost"
DEF_PEER_PORT = 12345


class usbUDP:

    def __init__(self, max_packet=512):
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.to_port = DEF_PEER_PORT
        self.to_ip = DEF_PEER_IP
        self.curr_timeout = None
        self.is_connected = False
        self.max_packet = max_packet
        self.my_seq_num = 1
        self.last_sent = None
        self.last_recv = None
        self.one_byte_struct = struct.Struct('B')

        # Use two different buffers
        #  (to be able to find retransmissions without copying)

        self.buffer1 = bytearray(65535)
        self.buffer1_mv = memoryview(self.buffer1)

        self.buffer2 = bytearray(65535)
        self.buffer2_mv = memoryview(self.buffer2)

        self.prev_len = 0
        self.buff_num = 1

    # Send a packet to the existing peer (used by clients)
    def send_packet(self, packet):

        if not self.is_connected:
            self.connect()

        self.last_sent = self.one_byte_struct.pack(self.my_seq_num) + packet
        still_ok = self.my_socket.send(self.last_sent)

        self.my_seq_num = (self.my_seq_num + 1) % 256

        return still_ok

    def connect(self, remote_ip=None, remote_port=None):
        if remote_ip is None:
            remote_ip = self.to_ip

        if remote_port is None:
            remote_port = self.to_port

        self.my_socket.connect((remote_ip, remote_port))
        self.is_connected = True

    def receive_packet(self, timeout=None):

        if not self.is_connected:
            self.connect()

        # Alternate between the two buffers
        #  for each NEW packet received
        if self.buff_num == 1:
            curr_buff_mv = self.buffer1_mv
            prev_buff_mv = self.buffer2_mv
        else:
            curr_buff_mv = self.buffer2_mv
            prev_buff_mv = self.buffer1_mv

        # If the timeout is different than last time, then change it
        if timeout != self.curr_timeout:
            self.my_socket.settimeout(timeout)
            self.curr_timeout = timeout

        try:
            # Yes, this is likely larger than max packet
            retlen = self.my_socket.recv_into(curr_buff_mv, 65535)

        except socket.timeout:
            print("Timed out talking to the relay", file=sys.stderr)

            print("Timeout duration was", timeout, "(seconds)")
            print("Last packet sent was", self.last_sent)

            sys.exit(1)

        except ConnectionRefusedError:
            print("Connection to relay refused (is it running?)",
                  file=sys.stderr)
            sys.exit(1)

        except KeyboardInterrupt:
            print("Stopping due to receiving a ^C input", file=sys.stderr)
            sys.exit(0)

        # Too large?  Ignore it (max_packet is packet w/o seq #, so +1)
        if retlen > self.max_packet + 1:
            print("Too large frame received, ignoring", file=sys.stderr)
            print("My MaxPacket=", self.max_packet, "packet len=", retlen)

            packet = None

        # Received a duplicate packet?  ignore it
        elif (self.prev_len == retlen) and \
              (curr_buff_mv[:retlen] == prev_buff_mv[:retlen]):

            packet = None

        else:
            # Good and NEW packet

            packet = curr_buff_mv[1:retlen]  # Remove the sequence number

            # Update packet len to compare packets
            self.prev_len = retlen

            # Good packet - so update which buff is going to be used next
            if self.buff_num == 1:
                self.buff_num = 2
            else:
                self.buff_num = 1

        return packet

    def set_port(self, newPort):
        self.to_port = newPort

    def set_ip(self, newIP):
        self.to_ip = newIP

    def get_max_packet(self):
        return self.max_packet

    def setMaxPacket(self, new_size=-1):

        old_size = self.max_packet

        # Force a min packet size
        #  (also is the default if new_size = -1)
        if new_size < 64:
            new_size = 8192

        self.max_packet = new_size

        return (old_size, new_size)
