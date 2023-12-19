import usb1

import ctypes
import select
import os
import sys
import threading
import time

VENDOR_ID = 0xca7e
PRODUCT_ID = 0xca7e


class usbUSB1:

    #
    #   Event checker is needed to handle the hotplug callback
    #   when there is not a lot of activity with the USB port
    #
    def _event_checker(self, context):
        while True:
            context.handleEventsTimeout()
            time.sleep(10)

    def _hotplug_callback(self, context, device, event):
        #print("Context:", context)
        #print("Device:", device)
        #print("Event:", event)

        if device == self.dev.getDevice():
            print("USB device was disconnected, exiting...")
            os._exit(1)

        return False        # Keep registered

    # dev, usb1.ENDPOINT_IN | 1, usb1.ENDPOINT_OUT | 2, 512)
    def __init__(self, dev=None,
                 in_endpoint=usb1.ENDPOINT_IN | 1,
                 out_endpoint=usb1.ENDPOINT_OUT | 1,
                 max_packet=512,    # Default - tries to match remote server
                 bulkSize=512,     # Default to FS/HS size
                 vendor_id=VENDOR_ID,
                 product_id=PRODUCT_ID):

        if dev is None:
            context = usb1.USBContext()

            if context is not None:
                dev = context.openByVendorIDAndProductID(vendor_id, product_id)

            else:
                print("Could not create a USB context", file=sys.stderr)
                sys.exit(1)

            if dev is None:
                print("Error: Could not find the proper USB device for",
                      hex(vendor_id), hex(product_id), file=sys.stderr)
                sys.exit(1)

            #print("Claiming", file=sys.stderr)
            dev.claimInterface(0)
            #print("Claimed", file=sys.stderr)

        self.dev = dev
        self.in_endpoint = in_endpoint
        self.out_endpoint = out_endpoint
        self.max_packet = max_packet      # Max size for a USB bulk transaction
        self.bulkSize = bulkSize        # Max size of a USB bulk packet

        self.buffer = bytearray(self.max_packet)
        self.buffer_mv = memoryview(self.buffer)

        self.buffer_char = None
        self.buffer_char_t = None

        if context.hasCapability(usb1.libusb1.LIBUSB_CAP_HAS_HOTPLUG):
            context.hotplugRegisterCallback(
                self._hotplug_callback,
                vendor_id=vendor_id,
                product_id=product_id,
                events=usb1.libusb1.LIBUSB_HOTPLUG_EVENT_DEVICE_LEFT)

            t1 = threading.Thread(target=self._event_checker, args=[context])
            t1.daemon = True
            t1.start()

    def send_packet(self, data):
        still_ok = 1
        initial_send_failed = False
        pack_len = len(data)

        # Try to send it - if it fails, then see if there is an outstanding
        # read request
        try:
            num_bytes = self.dev.bulkWrite(self.out_endpoint, data, 1000)

        except usb1.USBErrorTimeout:
            initial_send_failed = True

        if initial_send_failed:
            print(
                "Failed initial send - looking for previous incomplete transaction",
                file=sys.stderr)

            try:
                junk = self.receive_packet(1)

            except usb1.USBErrorTimeout:
                print("No outstanding data found", file=sys.stderr)

            else:
                print("Found outstanding data, continuing...", file=sys.stderr)

            num_bytes = self.dev.bulkWrite(self.out_endpoint, data)

        # Do I need to end with a ZLP?  If so, do it
        #  (this is if the last packet in a transaction is full sized)

        if (pack_len != self.max_packet) and (pack_len % self.bulkSize == 0):
            self.dev.bulkWrite(self.out_endpoint, b"")

        if num_bytes != pack_len:
            print("Error sending data packet", os.strerror(num_bytes))
            still_ok = 0

        return still_ok

    def receive_packet(self, timeout=None):
        if timeout is None:
            timeout = 0
        else:
            timeout = int(timeout * 1000)   # Convert from seconds to ms

        # Initialize the "ctype view" of the buffer, but only
        #  once
        if self.buffer_char is None:
            self.buffer_char_t = ctypes.c_char * len(self.buffer)
            self.buffer_char = self.buffer_char_t.from_buffer(self.buffer)

        # self, endpoint, data, length, timeout
        retlen = self.dev._bulkTransfer(
            self.in_endpoint,
            self.buffer_char,
            self.max_packet,
            timeout)

        # data = self.dev.bulkRead(self.in_endpoint,
        #                         self.buffer_char,
        #                         timeout)

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

        # Allow the _char to be recreated
        self.buffer_char = None
        self.buffer_char_t = None

        return (old_size, new_size)
