from ctypes import *

USB_DT_SS_ENDPOINT_COMP = 0x30


# A structure representing the standard USB device descriptor. This
# descriptor is documented in section 9.6.1 of the USB 2.0 specification.
# All multiple-byte fields are represented in host-endian format.
class libusb_device_descriptor(Structure):
    _pack_ = 1
    _fields_ = [
        # Size of this descriptor (in bytes)
        ('bLength', c_uint8),
        # Descriptor type. Will have value LIBUSB_DT_DEVICE in this
        # context.
        ('bDescriptorType', c_uint8),
        # USB specification release number in binary-coded decimal. A
        # value of 0x0200 indicates USB 2.0, 0x0110 indicates USB 1.1,
        # etc.
        ('bcdUSB', c_uint16),
        # USB-IF class code for the device. See libusb_class_code.
        ('bDeviceClass', c_uint8),
        # USB-IF subclass code for the device, qualified by the
        # bDeviceClass value
        ('bDeviceSubClass', c_uint8),
        # USB-IF protocol code for the device, qualified by the
        # bDeviceClass and bDeviceSubClass values
        ('bDeviceProtocol', c_uint8),
        # Maximum packet size for endpoint 0
        ('bMaxPacketSize0', c_uint8),
        # USB-IF vendor ID
        ('idVendor', c_uint16),
        # USB-IF product ID
        ('idProduct', c_uint16),
        # Device release number in binary-coded decimal
        ('bcdDevice', c_uint16),
        # Index of string descriptor describing manufacturer
        ('iManufacturer', c_uint8),
        # Index of string descriptor describing product
        ('iProduct', c_uint8),
        # Index of string descriptor containing device serial number
        ('iSerialNumber', c_uint8),
        # Number of possible configurations
        ('bNumConfigurations', c_uint8)]

class libusb_endpoint_descriptor(Structure):
    _pack_ = 1
    _fields_ = [
        ('bLength', c_uint8),
        ('bDescriptorType', c_uint8),
        ('bEndpointAddress', c_uint8),
        ('bmAttributes', c_uint8),
        ('wMaxPacketSize', c_uint16),
        ('bInterval', c_uint8),
        ('bRefresh', c_uint8),
        ('bSynchAddress', c_uint8)
        ]

class libusb_endpoint_descriptor_noaudio(Structure):
    _pack_ = 1
    _fields_ = [
        ('bLength', c_uint8),
        ('bDescriptorType', c_uint8),
        ('bEndpointAddress', c_uint8),
        ('bmAttributes', c_uint8),
        ('wMaxPacketSize', c_uint16),
        ('bInterval', c_uint8)
        ]

class libusb_interface_descriptor(Structure):
    _pack_ = 1
    _fields_ = [
        ('bLength', c_uint8),
        ('bDescriptorType', c_uint8),
        ('bInterfaceNumber', c_uint8),
        ('bAlternateSetting', c_uint8),
        ('bNumEndpoints', c_uint8),
        ('bInterfaceClass', c_uint8),
        ('bInterfaceSubClass', c_uint8),
        ('bInterfaceProtocol', c_uint8),
        ('iInterface', c_uint8)
        ]

class libusb_config_descriptor(Structure):
    _pack_ = 1
    _fields_ = [
        ('bLength', c_uint8),
        ('bDescriptorType', c_uint8),
        ('wTotalLength', c_uint16),
        ('bNumInterfaces', c_uint8),
        ('bConfigurationValue', c_uint8),
        ('iConfiguration', c_uint8),
        ('bmAttributes', c_uint8),
        ('bMaxPower', c_uint8)
        ]



class libusb_ss_ep_comp_descriptor(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [ ('bLength', c_uint8),
                ('bDescriptorType', c_uint8),
                ('bMaxBurst', c_uint8),
                ('bAttributes', c_uint8),
                ('wBytesPerInterval', c_uint16) ]

