# pip3 install ioctl-opt
import ioctl_opt

from ctypes import *

#usb_gadgetfs_event_type
GADGETFS_NOP = 0
GADGETFS_CONNECT = 1
GADGETFS_DISCONNECT = 2
GADGETFS_SETUP = 3
GADGETFS_SUSPEND = 4

#usb_device_speed
USB_SPEED_UNKNOWN = 0
USB_SPEED_LOW = 1   # usb 1.1
USB_SPEED_FULL = 2  # usb 1.1
USB_SPEED_HIGH = 3  # usb 2.0
USB_SPEED_WIRELESS = 4 # wireless (usb 2.5)
USB_SPEED_SUPER = 5 # usb 3.0
USB_SPEED_SUPER_PLUS = 6 # usb 3.1

class usb_ctrlrequest(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [ ('bRequestType', c_uint8),
                ('bRequest', c_uint8),
                ('wValue', c_uint16),
                ('wIndex', c_uint16),
                ('wLength', c_uint16) ]

class usb_gadgetfs_event_union(Union):
    _fields_ = [
            ('speed', c_uint32),
            ('setup', usb_ctrlrequest) ]


class usb_gadgetfs_event(LittleEndianStructure):
    _fields_ = [
            ('u', usb_gadgetfs_event_union),
            ('type', c_uint32) ]


GADGETFS_FIFO_STATUS = ioctl_opt.IO(ord('g'), 1)
GADGETFS_FIFO_FLUSH  = ioctl_opt.IO(ord('g'), 2)
GADGETFS_CLEAR_HALT  = ioctl_opt.IO(ord('g'), 3)

#print("ctrlrequest",sizeof(usb_ctrlrequest))
#print("event.u", sizeof(usb_gadgetfs_event_union))
#print("event", sizeof(usb_gadgetfs_event))

