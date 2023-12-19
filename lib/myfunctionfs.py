# pip3 install ioctl-opt
#  (may need apt install python3-pip)
import ioctl_opt

from ctypes import *


FUNCTIONFS_DESCRIPTORS_MAGIC = 1
FUNCTIONFS_STRINGS_MAGIC = 2
FUNCTIONFS_DESCRIPTORS_MAGIC_V2 = 3

FUNCTIONFS_HAS_FS_DESC = 1
FUNCTIONFS_HAS_HS_DESC = 2
FUNCTIONFS_HAS_SS_DESC = 4
FUNCTIONFS_HAS_MS_OS_DESC = 8
FUNCTIONFS_VIRTUAL_ADDR = 16
FUNCTIONFS_EVENTFD = 32
FUNCTIONFS_ALL_CTRL_RECIP = 64
FUNCTIONFS_CONFIG0_SETUP = 128


# enum usb_functionfs_event_type {...}
FUNCTIONFS_BIND = 0
FUNCTIONFS_UNBIND = 1

FUNCTIONFS_ENABLE = 2
FUNCTIONFS_DISABLE = 3

FUNCTIONFS_SETUP = 4
FUNCTIONFS_SUSPEND = 5
FUNCTIONFS_RESUME = 6

class usb_ctrlrequest(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [ ('bRequestType', c_uint8),
                ('bRequest', c_uint8),
                ('wValue', c_uint16),
                ('wIndex', c_uint16),
                ('wLength', c_uint16) ]

class usb_functionfs_event_union(Union):
    _fields_ = [
                ('setup', usb_ctrlrequest)
                ]

class usb_functionfs_event(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
            ('u', usb_functionfs_event_union),
            ('type', c_uint8),
            ('pad', c_uint8 * 3)
                ]

class usb_functionfs_descs_head_v2(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
            ('magic', c_uint32),
            ('length', c_uint32),
            ('flags', c_uint32)
            ]


class usb_functionfs_strings_head(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
            ('magic', c_int32),
            ('length', c_int32),
            ('str_count', c_int32),
            ('lang_count', c_int32)
            ]


FUNCTIONFS_FIFO_STATUS = ioctl_opt.IO(ord('g'), 1)
FUNCTIONFS_FIFO_FLUSH  = ioctl_opt.IO(ord('g'), 2)
FUNCTIONFS_CLEAR_HALT  = ioctl_opt.IO(ord('g'), 3)

FUNCTIONFS_INTERFACE_REVMAP  = ioctl_opt.IO(ord('g'), 128)
FUNCTIONFS_ENDPOINT_REVMAP  = ioctl_opt.IO(ord('g'), 129)
#FUNCTIONFS_ENDPOINT_DESC  = ioctl_opt.IO(ord('g'), 130)
