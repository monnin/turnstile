import os
import select


class usbOSIf:

    def __init__(self, in_fd, out_fd, max_packet, bulkSize=512):
        self.in_fd = in_fd
        self.out_fd = out_fd

        self.bulkSize = bulkSize    # Size of individual USB bulk packets

        self.max_packet = max_packet  # Size of largest USB bulk transaction

        self.buffer = bytearray(self.max_packet)
        self.buffer_mv = memoryview(self.buffer)

    def send_packet(self, packet):
        still_ok = 1
        pack_len = len(packet)

        num_bytes = os.write(self.out_fd, packet)

        # Do I need to end with a ZLP?  If so, do it
        #  (this is if the last packet in a transaction is full sized)

        if (pack_len != self.max_packet) and (pack_len % self.bulkSize == 0):
            os.write(self.out_fd, b"")

        if num_bytes != pack_len:
            print("Error sending data packet", os.strerror(num_bytes))
            still_ok = 0

        return still_ok

    def receive_packet(self, timeout=None):
        still_ok = True

        if timeout is not None:
            # timeout in seconds
            (r, w, e) = select.select([self.in_fd], [], [], timeout)

            still_ok = self.in_fd in r

        if still_ok:
            num_bytes = os.readv(self.in_fd, [self.buffer_mv])

            return self.buffer_mv[:num_bytes]
        else:
            return None

    def get_max_packet(self):
        return self.max_packet

    def setMaxPacket(self, new_size=-1):

        old_size = self.max_packet

        # Force a min packet size
        #  (also is the default if new_size = -1)
        if new_size < 64:
            new_size = 8192

        self.max_packet = new_size
        self.buffer = bytearray(self.max_packet)
        self.buffer_mv = memoryview(self.buffer)

        return (old_size, new_size)
