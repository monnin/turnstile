import sys
import usb.core
import usb.util

VENDOR_ID = 0xca7e
PRODUCT_ID = 0xca7e


class usbUSB:

    # dev, usb1.ENDPOINT_IN | 1, usb1.ENDPOINT_OUT | 2, 512)
    def __init__(self, dev=None,
                 #in_endpoint = usb.util.ENDPOINT_IN | 1,
                 #out_endpoint = usb.util.ENDPOINT_OUT | 1,
                 max_packet=512,    # Default - might change if superspeed
                 vendor_id=VENDOR_ID,
                 product_id=PRODUCT_ID):

        dev = usb.core.find(idVendor=vendor_id,
                            idProduct=product_id)
        if dev is None:
            print("Error: Could not find the proper USB device for",
                  hex(vendor_id), hex(product_id), file=sys.stderr)
            sys.exit(1)

        #print("Claiming", file=sys.stderr)
        # dev.claimInterface(0)
        #print("Claimed", file=sys.stderr)

        self.dev = dev
        #self.in_endpoint = in_endpoint
        #self.out_endpoint = out_endpoint

        self.max_packet = max_packet

        self.buffer = bytearray(self.max_packet)
        self.buffer_mv = memoryview(self.buffer)

        self.buffer_char = None

    def send_packet(self, data):
        still_ok = 1

        num_bytes = self.dev.write(1, data)

        if num_bytes != len(data):
            print("Error sending data packet", os.strerror(num_bytes))
            still_ok = 0

        return still_ok

    def receive_packet(self, timeout=None):

        retlen = self.dev.read(self.buffer, timeout)
        print("Got", retlen, self.buffer)

        if retlen is None:
            data = None
        else:
            data = self.buffer_mv[:retlen]

        return data

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
