#
#   Used for testing of the code without needing an active USB connection
#


class usbNull:

    def __init__(self):
        self.max_packet = 512

    def send_packet(self, data):
        print(">", data)

    def receive_packet(self, timeout=None):
        data = input("<")

        # Return a memoryview to be consistent with the other low-level classes
        return memoryview(date.encode())

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
