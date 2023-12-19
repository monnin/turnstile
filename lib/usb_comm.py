import hashlib
import io
import os
import random
import stat
import struct
import sys
import threading
import time
import traceback

MAX_FILE_PATHLEN = 4096

MAX_TRANSACTIONS = 100
MAX_CURR_TIME = 5000

DEF_DEBUG = 1


class USBComm:
    def __init__(self, raw_port=None, timeout=0):
        self.raw_port = raw_port
        self.timeout = timeout

        # This is only needed if USBComm is being instatiated vs. a sub-class
        if raw_port is not None:
            self.max_packet = raw_port.max_packet

        self.debug = DEF_DEBUG
        self.last_sent = None

        # Speedup - Compile the structure once
        self.stat_struct = struct.Struct("<BHLLL")
        self.one_byte_struct = struct.Struct("B")

        # Variables for the stat() cache (often set by os.scandir)

        self.clock_thread = None
        self.stop_threads = False
        self.curr_time = 0
        self.stat_cache = {}

    def send_packet(self, data):
        self.print_debug(5, "Sending: ", data)
        self.last_sent = data

        try:
            retval = self.raw_port.send_packet(data)

        except Exception as my_except:
            print("usb_comm::send_packet failed", my_except)
            print("Trying to send:", data)
            print("Timeout was", self.timeout)
            traceback.print_exc()  # Print the traceback

            os._exit(1)

        self.print_debug(5, "send_packet returned", retval)

        return retval

    def receive_packet(self):
        get_more = True

        while get_more:
            try:
                data = self.raw_port.receive_packet(timeout=self.timeout)

            except KeyboardInterrupt:
                print("Ctrl-C caught, exiting", file=sys.stderr)
                os._exit(0)

            except Exception as my_except:
                print("usb_comm::receive_packet failed", my_except)
                print("Last USB packet sent:", self.last_sent)
                print("Timeout was", self.timeout)
                traceback.print_exc()  # Print the traceback

                os._exit(1)

            if data is None:
                print("Got None")

                self.print_debug(4, "receive_packet returned None")
                get_more = False

            elif len(data) == 0:
                print("Got ZLP")

                self.print_debug(4, "Received a Zero-Length-Packet, " +
                                 "skipping to next transaction")

            elif isinstance(data, memoryview):
                self.print_debug(5, "Received: ", data.tobytes())
                get_more = False

            else:
                self.print_debug(5, "Received: ", data)
                get_more = False

        return data

    # Send one package and receive one packet

    def send_and_receive_packet(self, data):
        self.send_packet(data)

        return self.receive_packet()

    def print_debug(self, level, *args, **kwargs):
        if self.debug >= level:
            print(*args, **kwargs)

    def set_debug(self, newlevel):
        self.debug = newlevel

    #
    # ----------------------------------------------------------------------
    #

    #  update_curr_time - this is supposed to be a target of a thread
    def update_curr_time(self):
        cleanup_countdown = 60

        while not self.stop_threads:

            # Regularly roll over time to keep time from getting "too" large
            if self.curr_time >= MAX_CURR_TIME - 1:
                self.curr_time = 0
            else:
                self.curr_time += 1

            cleanup_countdown -= 1

            if cleanup_countdown <= 0:
                self.cleanup_stat_cache()

            time.sleep(1)

    def time_too_old(self, obj_time, max_time):
        diff = self.curr_time - obj_time

        # Did a time rollover happen?
        if diff < 0:
            diff += MAX_CURR_TIME

        return diff > max_time

    def get_filestat_w_cache(self, path, max_time=300):
        stat_res = None

        # Start the cache cleanup thread if necessary
        if self.clock_thread is None:

            self.stop_threads = False

            self.clock_thread = threading.Thread(target=self.update_curr_time)
            self.clock_thread.daemon = True   # Die with the main thread

            self.clock_thread.start()

        if path in self.stat_cache:
            (obj_time, stat_res) = self.stat_cache[path]

            # Don't use if more than 5 minutes old
            if self.time_too_old(obj_time, max_time):
                del self.stat_cache[path]
                stat_res = None

        if stat_res is None:

            try:
                stat_res = os.stat(path)
                # Now cache the result
                self.stat_cache[path] = (self.curr_time, stat_res)

            except Exception as my_except:
                stat_res = None

        return stat_res

    def cleanup_stat_cache(self, max_time=300, force_delete=False):
        oldest_time = None
        oldest_path = None

        delete_count = 0

        # Convert the keys into a list so that we
        #   can delete items as we go through the
        #   dictionary
        for k in list(self.stat_cache):
            (obj_time, stat_res) = self.stat_cache[k]

            diff = self.curr_time - obj_time

            # Did a time rollover happen?
            if diff < 0:
                diff += MAX_CURR_TIME

            if diff > max_time:
                delete_count += 1
                del self.stat_cache[k]

            elif (oldest_path is None) or (diff > oldest_time):
                oldest_time = diff
                oldest_path = k

        if (delete_count == 0) and (oldest_path is not None):
            delete_count += 1
            del self.stat_cache[oldest_path]

        return delete_count

    def stop_all_threads(self):
        self.stop_threads = True

        if self.clock_thread is not None:
            self.clock_thread.join(timeout=2)

            self.clock_thread = None

    #
    # ----------------------------------------------------------------------
    #
    # (is_dir, mode, size, mtime, ctime)

    def stat_file_helper(self, path, initialpath=None):
        result = None

        if initialpath is None:
            initialpath = path

        stat_res = self.get_filestat_w_cache(path)

        if stat_res is not None:
            flags = stat.S_ISDIR(stat_res.st_mode)

            is_file = stat.S_ISREG(stat_res.st_mode)
            if is_file:
                flags = flags | 0x02

            mode = stat.S_IMODE(stat_res.st_mode)

            size = stat_res.st_size

            mtime = int(stat_res.st_mtime)
            ctime = int(stat_res.st_ctime)

            # Add on the symlink to the (old is_dir) flags
            if os.path.islink(initialpath):
                flags = flags | 0x80

            result = (flags, mode, size, mtime, ctime)

        return result

    #
    # Convert a symlink into a full absolute path
    #  (even if the destination is a relative path)
    #

    def readAndConvertLink(self, path, currdir):
        destlink = None

        destlink = os.readlink(path)

        if not os.path.isabs(destlink):
            destlink = os.path.join(currdir, destlink)
            destlink = os.path.realpath(destlink)

        return destlink

    def compute_hash(self, realpath):
        result = None

        if os.path.isfile(realpath):
            f = open(realpath, "rb")
            #
            # hashlib.file_digest is new in hashlib 3.11
            #   (but that version isn't as common as I'd like just yet)
            #
            #hash_res = hashlib.file_digest(f, "sha512")

            hash_res = hashlib.sha512(f.read())
            f.close()

            if hash_res is not None:
                result = hash_res.hexdigest()

        return result

#
# ----------------------------------------------------------------------
#


class Client(USBComm):
    def __init__(self, raw_port, timeout):
        USBComm.__init__(self, raw_port, timeout)

        self.client_set_max_packet(self.client_get_max_packet())

    def client_reset(self):
        self.send_packet(b"Z")      # Send a reset

        # Grab all data until a timeout
        while self.receive_packet() is not None:
            pass

    def __client_send_cmd(self, cmd, data=b""):
        still_ok = 1

        start = 0
        whole_len = len(data)

        while (still_ok != 0) and (whole_len - start + 1 > self.max_packet):
            data = self.send_and_receive_packet(
                b"P" + data[start:start + self.max_packet])

            if (data is None) or (data[0] != b"c"):
                print("Did not get a 'continue' response when sending",
                      cmd, data, file=sys.stderr)

                # If this wasn't a timeout - then issue a reset
                if data is not None:
                    self.client_reset()

                still_ok = 0

            start = start + self.max_packet - 1

        if still_ok:
            still_ok = self.send_packet(cmd + data[start:])

        return still_ok

    def client_set_max_packet(self, new_size=-1):
        self.print_debug(4, "Setting Client's max_packet to", new_size)
        if new_size < 64:
            new_size = 8192  # Default size

        self.max_packet = new_size
        self.raw_port.setMaxPacket(new_size)

        return new_size

    def client_get_port_max_packet(self):
        return self.raw_port.get_max_packet()
#
# ----------------------------------------------------------------------
#

    def __client_send_cmd_and_receive_all(self, cmd, path=b"", callback=None):

        whole_data = bytearray(0)

        still_ok = self.__client_send_cmd(cmd, path)

        while still_ok:
            one_packet = self.receive_packet()
            # Received a too small packet? then abort

            if (one_packet is None) or (len(one_packet) < 2):
                still_ok = 0               # Runt! Abort

                # If this wasn't a timeout - then issue a reset
                if one_packet is not None:
                    self.client_reset()      # Send a reset

                whole_data = None
            else:
                resp = chr(one_packet[0])

                # Get the payload
                #
                #  Return it one of two ways:
                #
                #   1 - via a callback function
                #   2 - As a single response

                if callback is not None:
                    # Get an error?  then return an error
                    if resp == "z":
                        callback(None)
                    else:
                        callback(one_packet[2:])

                else:
                    whole_data.extend(one_packet[2:])

                if resp == "d":
                    # Ask for next packet
                    still_ok = self.send_packet(b"C" + one_packet[1:2])

                elif resp == "l":
                    still_ok = 0          # last data packet

                elif resp == "z":
                    still_ok = 0          # error packet
                    whole_data = None

                else:
                    still_ok = 0          # Unknown response
                    whole_data = None

                    print("Unknown reponse received, sent",
                          cmd, path, "received", one_packet,
                          file=sys.stderr)

        if callback is not None:
            result = still_ok
        else:
            result = whole_data

        return result


#
# ----------------------------------------------------------------------
#


    def __client_send_cmd_and_receive_all_yield(self, cmd, path=b"", as_bytes=False):

        still_ok = self.__client_send_cmd(cmd, path)

        while still_ok:
            one_packet = self.receive_packet()
            # Received a too small packet? then abort

            if (one_packet is None) or (len(one_packet) < 2):
                still_ok = 0               # Runt! Abort

                # If this wasn't a timeout - then issue a reset
                if one_packet is not None:
                    self.client_reset()      # Send a reset

                last_response = None
            else:
                resp = chr(one_packet[0])

                self.print_debug(5, "Yielding", one_packet[2:])

                if as_bytes:
                    yield bytes(one_packet[2:])
                else:
                    yield one_packet[2:]

                if resp == "d":
                    # Ask for next packet
                    still_ok = self.send_packet(b"C" + one_packet[1:2])

                elif resp == "l":
                    still_ok = 0          # last data packet
                    last_response = b""

                elif resp == "z":
                    last_response = None
                    still_ok = 0          # error packet

                else:
                    last_response = None
                    still_ok = 0          # Unknown response

                    print("Unknown reponse received, sent",
                          cmd, path, "received", one_packet,
                          file=sys.stderr)

        # return last_response

    def client_noop(self, val=None):
        self.print_debug(3, "Sending NoOp Command")

        ret = None

        if val is None:
            ret = self.__client_send_cmd_and_receive_all(b"N")

        # Send only one-byte values
        elif (val >= 0) and (val <= 255):
            ret = self.__client_send_cmd_and_receive_all(
                b"N" + self.one_byte_struct.pack(val))

        return ret

    def client_verify_server(self, val=None):
        """Simple check to see if the server responds)"""

        try:
            ret = self.client_noop(val)

        except Exception as my_except:
            ret = None

        return ret is not None

    def client_set_priority(self, new_priority):
        self.print_debug(3, "Sending SetPriority Command")

        return self.__client_send_cmd_and_receive_all(
            b"Q" + self.one_byte_struct.pack(new_priority))

    def client_ls(self, pathname, dir_only=False):
        self.print_debug(3, "Sending LS Command, arg=", pathname)

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        data = self.__client_send_cmd_and_receive_all(b"L", pathname)

        if data is not None:
            data = data.decode('latin1')

            # Special case two \0\0 == a file and it was found
            if data == "\0\0":
                if dir_only:
                    data = None
                else:
                    data = os.path.basename(pathname)

            # Empty data string?  Return just an empty list
            elif len(data) == 0:
                data = []

            else:
                data = data.split("\0")

        return data

    def client_get_file(self, pathname):
        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        self.print_debug(3,
                         "Sending GetFile Command, arg=", pathname)

        # Returns as bytes() not a str()
        return self.__client_send_cmd_and_receive_all(b"G", pathname)

    def client_hash_file(self, pathname):
        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        self.print_debug(3,
                         "Sending HashFile Command, arg=", pathname)

        # Returns as bytes() not a str()
        res = self.__client_send_cmd_and_receive_all(b"H", pathname)

        # Got a valid-ish hash back?  Convert it into a str()
        if res is not None:
            res = res.decode('latin1')

        return res

    # Comare a local file's hash to a remote file's hash
    #  and return a value (along with both hashes).   Return values:
    #
    #   0 - identical files
    #   1 - different files
    #   2 - local file not found (checked first)
    #   3 - remote file not found

    def client_compare_hash_file(self, localpath, remotepath):
        remote_res = None
        local_res = self.compute_hash(localpath)

        if local_res is None:
            res = 2  # Local file not found

        else:
            remote_res = self.client_hash_file(remotepath)

            if remote_res is None:
                res = 3  # Remote file not found

            elif local_res == remote_res:
                res = 0  # Same file

            else:
                res = 1  # Different file

        return (res, local_res, remote_res)

    def client_get_fileYield(self, pathname, as_bytes=False):
        self.print_debug(3,
                         "Sending GetFile Command with yield, arg=", pathname)

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        # Returns as bytes() not a str()
        return self.__client_send_cmd_and_receive_all_yield(b"G",
                                                    pathname, as_bytes)

    def client_get_fileCB(self, pathname, callback):
        still_ok = 1

        self.print_debug(
            3,
            "Sending GetFile Command with callback, arg=",
            pathname)

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        result = self.__client_send_cmd_and_receive_all(b"G",
                                                 pathname, callback)

        if result is None:
            still_ok = 0

        return still_ok

    def client_get_max_packet(self):
        self.print_debug(3, "Sending GetMaxPacket() Command")

        data = self.__client_send_cmd_and_receive_all(b"M")

        if data is not None:
            data = data[0] + (data[1] * 256) + (data[2] * 256**2) + \
                (data[3] * 256**3)

        return data

    def client_get_symlink(self, pathname):
        self.print_debug(3, "Sending GetSymlink() Command, arg=", pathname)

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        data = self.__client_send_cmd_and_receive_all(b"K", pathname)

        if isinstance(data, bytearray):
            data = bytes(data)

        return data

    #
    # (is_dir, mode, size, mtime, ctime)
    #
    # mtime and ctime are truncated to whole seconds only
    #
    def client_stat_path(self, pathname):
        self.print_debug(3, "Sending Stat() Command, arg=", pathname)

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        data = self.__client_send_cmd_and_receive_all(b"S", pathname)
        if data is not None:
            #(flags, mode, size, mtime, ctime) = struct.unpack("<BHLLL", data)
            #data = (flags, mode, size, mtime, ctime)

            data = self.stat_struct.unpack(data)

        self.print_debug(4, "stat() returned", data)

        return data

    def client_stat_pathToDict(self, pathname):
        new_dict = None

        data = self.client_stat_path(pathname)

        if data is not None:
            (flags, mode, size, mtime, ctime) = data
            new_dict = {}

            new_dict['is_dir'] = flags & 0x01
            new_dict['is_symlink'] = flags & 0x80

            new_dict['flags'] = flags
            new_dict['mode'] = mode
            new_dict['size'] = size
            new_dict['mtime'] = mtime
            new_dict['ctime'] = ctime

        return new_dict

    def client_local_stat_path(self, pathname):
        result = None

        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        stat_res = self.stat_file_helper(pathname)

        if stat_res is not None:
            result = stat_res

        return result

#
# ----------------------------------------------------------------------
#
    def client_local_stat_pathToDict(self, pathname):
        if isinstance(pathname, str):
            pathname = pathname.encode('latin1')

        result = None

        stat_res = self.stat_file_helper(pathname)

        if stat_res is not None:
            (flags, mode, size, mtime, ctime) = stat_res

            result = {}

            result["is_dir"] = flags & 0x01
            result["is_symlink"] = flags & 0x80
            result["is_file"] = flags & 0x02

            result["flags"] = flags
            result["mode"] = mode
            result["size"] = size
            result["mtime"] = mtime
            result["ctime"] = ctime

        return result


#
# ----------------------------------------------------------------------
#

class Server(USBComm):
    def __reset_buffers(self):
        self.buffer = [None] * MAX_TRANSACTIONS
        self.init_time = [0] * MAX_TRANSACTIONS
        self.buff_start = [0] * MAX_TRANSACTIONS
        self.buff_len = [0] * MAX_TRANSACTIONS

    def __init__(self, raw_port, timeout):
        self.__reset_buffers()
        self.good_prefixes = []

        self.packet_buffer = bytearray(raw_port.max_packet)
        self.packet_mv = memoryview(self.packet_buffer)

        USBComm.__init__(self, raw_port, timeout)

#
# ----------------------------------------------------------------------
#
    def add_slash(self, p):
        if isinstance(p, str):
            p = p.encode("latin1")

        if not p.endswith(b"/"):
            p = p + b"/"

        return p

    def add_prefix_entry(self, real_p, alias_p):
        if isinstance(real_p, str):
            real_p = real_p.encode("latin1")

        if isinstance(alias_p, str):
            alias_p = alias_p.encode("latin1")

        self.good_prefixes.append([real_p, alias_p])

    def add_good_prefix(self, p):
        # Allow for the form of <real-path> <alias-path>+
        if isinstance(p, list):
            if len(p) == 1:
                real_p = self.add_slash(p[0])

                self.add_prefix_entry(real_p, real_p)
                self.print_debug(4, "Added GOOD_PREFIX", real_p)

            elif len(p) > 1:
                real_p = self.add_slash(p[0])

                for alias_p in p[1:]:
                    alias_p = self.add_slash(alias_p)

                    self.add_prefix_entry(real_p, alias_p)
                    self.print_debug(4, "Added GOOD_PREFIX", real_p, alias_p)

        elif isinstance(p, str):
            real_p = self.add_slash(p)
            self.good_prefixes.append([real_p, real_p])
            self.print_debug(4, "Added GOOD_PREFIX", real_p)

        else:
            print("Invalid path given to add_good_prefix",
                  p, "ignoring", file=sys.stderr)


#
# ----------------------------------------------------------------------
#

    # Convert any aliases into real paths


    def path_convert_aliases(self, p):

        slash_p = self.add_slash(p)

        for (real_p, alias_p) in self.good_prefixes:

            if p.startswith(alias_p):
                p = p.replace(alias_p, real_p, 1)
            elif p == alias_p:
                p = real_p
            elif slash_p == alias_p:
                p = real_p[:-1]

        return p

    def path_is_good(self, p):
        is_good = False

        # Unalias the path
        p = self.path_convert_aliases(p)

        # Convert to an absolute path
        p = os.path.realpath(p)

        for (one_prefix, alias_p) in self.good_prefixes:

            # Allow for access to the read directory itself too
            #  (the stored path ends with "/", so ignore that ending)
            if p.startswith(one_prefix) or (p == one_prefix[:-1]):
                is_good = True

        # Disallow non files and directories
        if (not os.path.isfile(p)) and (not os.path.isdir(p)):
            is_good = False

        # Extra check for symlinks that go out of a good section
        # if (is_good) and (os.path.islink(p)):
        #    (is_good, p2) = self.path_is_good(os.readlink(p))

        return (is_good, p)
#
# ----------------------------------------------------------------------
#

    def clear_one_slot(self, i):
        # If this is a file handle, then close it first
        if isinstance(self.buffer[i], io.BufferedReader):
            self.buffer[i].close()

        self.buffer[i] = None
        self.init_time[i] = 0
        self.buff_start[i] = 0
        self.buff_len[i] = 0

    def purge_old_buffers(self, purge_time=240):
        too_old = int(time.time() - purge_time)

        for i in range(0, MAX_TRANSACTIONS):
            # Delete transactions older than the purge time
            if self.init_time[i] < too_old:
                self.clear_one_slot(i)

    def find_free_slot_h(self):
        start = random.randint(1, MAX_TRANSACTIONS - 1)
        last = (start - 1) % MAX_TRANSACTIONS

        # Skip the zero slot
        if last == 0:
            last = 1

        i = start
        while (self.buffer[i] is not None) and (i != last):
            i = i + 1
            i = i % MAX_TRANSACTIONS

            # Skip slot 0
            if i == 0:
                i = 1

        # Did we run out of buffers?  if so, then return -1 as an error
        if self.buffer[i] is not None:
            i = -1

        return i

    #  Find a free slot, but try to purge if necessary
    def find_free_slot(self):
        free_slot = self.find_free_slot_h()

        if free_slot < 0:
            self.purge_old_buffers()
            free_slot = self.find_free_slot_h()

        return free_slot

    #
    # ----------------------------------------------------------------------
    #

    def server_send_one_packet(self, response, trans_id=0, data=b""):
        still_ok = 1

        # Double check to see if the resulting packet would be too big
        if len(data) + 2 > self.raw_port.max_packet:
            still_ok = 0

        else:
            still_ok = self.send_packet(response +
                                 self.one_byte_struct.pack(trans_id) +
                                 data)

        return still_ok

    def server_send_err_response(self):
        return self.server_send_one_packet(b"z")

    def __server_send_data_response(self, data=b""):
        still_ok = 1

        response = b"l"      # default=Last packet
        trans_id = 0         # default to no transaction (since single packet)

        whole_len = len(data)
        end = whole_len

        # Does the data (+ 2 byte header) NOT fit into a single packet?
        if whole_len + 3 > self.raw_port.max_packet:

            end = self.raw_port.max_packet - 2
            my_slot = self.find_free_slot()

            # Valid slot?
            if my_slot != -1:
                self.buffer[my_slot] = data[end:]

                # Record when created
                self.init_time[my_slot] = int(time.time())

                # At the beginning of the buffer
                self.buff_start[my_slot] = 0

                # What (how much) is left to buffer
                self.buff_len[my_slot] = whole_len - end

                response = b"d"

                # Convert to 1..MAX_TRANSACTIONS (vs. 0..MAX_TRANSACTIONS-1)
                trans_id = my_slot

            else:
                still_ok = 0
                self.server_send_err_response()

        # Check to see if it still possible to send the packet
        if still_ok != 0:
            still_ok = self.server_send_one_packet(response, trans_id, data[:end])

        return still_ok

    def __server_send_next_from_file(self, i):
        still_ok = 1

        if self.buffer[i] is None:
            still_ok = self.send_packet(b"l" + i.to_byte(1, 'little'))

        else:
            try:
                num_bytes = self.buffer[i].readinto(self.packet_mv[2:])

            except Exception as my_except:
                still_ok = 0

            if still_ok:
                # If we didn't use all of the buffer, then we are at the end

                if num_bytes < self.raw_port.max_packet - 2:
                    self.packet_buffer[0] = 108      # b"l"
                else:
                    self.packet_buffer[0] = 100      # b"d"

                self.packet_buffer[1] = i
                still_ok = self.send_packet(self.packet_mv[:num_bytes + 2])

                # Last packet?  If so, then clear after send
                if self.packet_buffer[0] == 108:
                    self.clear_one_slot(i)

        return still_ok

    def server_send_data_from_file(self, pathname):
        still_ok = 1

        (is_good, realpath) = self.path_is_good(pathname)

        # Reserve an empty buffer slot
        my_slot = self.find_free_slot()

        if is_good and os.path.isfile(realpath) and (my_slot != -1):
            try:
                f = open(pathname, "rb")

            except Exception as my_except:
                still_ok = 0

            if still_ok:
                self.buffer[my_slot] = f
                self.init_time[my_slot] = int(time.time())

                # Send the first segment of the file
                self.__server_send_next_from_file(my_slot)
        else:
            still_ok = 0

        if still_ok == 0:
            self.server_send_err_response()

        return still_ok


#
# ----------------------------------------------------------------------
#


    def __send_next_buff_section(self, i):

        start = self.buff_start[i]
        remain = self.buff_len[i] - start

        if remain + 2 <= self.raw_port.max_packet:
            end = start + remain

            still_ok = self.send_packet(b"l" +
                                 self.one_byte_struct.pack(i) +
                                 self.buffer[i][start:end])

            self.clear_one_slot(i)

        else:
            end = start + self.raw_port.max_packet - 2

            still_ok = self.send_packet(b"d" +
                                 self.one_byte_struct.pack(i) +
                                 self.buffer[i][start:end])

            # Problem sending?  If so, abort this transaction
            if still_ok == 0:
                self.clear_one_slot(i)

            # Update pointer to location
            self.buff_start[i] = end

        return still_ok

#
# ----------------------------------------------------------------------
#

    def __server_send_next_buffer_block(self, trans_id):
        still_ok = 1

        if (trans_id < 1) or (trans_id > MAX_TRANSACTIONS):
            still_ok = 0
            self.server_send_err_response()

        # Already at the end?  Then just send an empty last data packet
        elif self.buffer[trans_id] is None:
            still_ok = self.send_packet(b"l" + self.one_byte_struct.pack(trans_id))

        # More data to send?
        else:
            if isinstance(self.buffer[trans_id], io.BufferedReader):
                still_ok = self.__server_send_next_from_file(trans_id)

            else:
                still_ok = self.__send_next_buff_section(trans_id)

        return still_ok

    def server_get_cmd_full_path_or_id(self):
        path = b""
        still_ok = 1

        data = self.receive_packet()

        while (still_ok != 0) and (data[0] == b"P") and \
               (len(path) < MAX_FILE_PATHLEN):

            path = path + data[1:]

            # Indicate ready for next packet
            still_ok = self.send_packet(b"c")

            if still_ok:
                data = self.receive_packet()

        cmd = chr(data[0])

        if (cmd == "C") or (cmd == "Q"):
            path = data[1]            # Not actually a path, but an "ID"
        else:
            path = path + data[1:]

            if len(path) >= MAX_FILE_PATHLEN:

                print("Too long of a path given for cmd",
                      cmd, path, file=sys.stderr)
                still_ok = 0

        if still_ok:
            return (cmd, path)

        else:
            self.server_send_err_response()
            return (None, None)


    def __server_handle_list_dir(self, realpath):
        """Handle the "ls" requests that point to a directory"""

        #
        # For a directory, provide a list of files in that directory
        #
        buff = bytearray(0)

        still_ok = 1

        try:
            files = os.listdir(realpath)
        except Exception as my_except:
            still_ok = 0

        if still_ok:
            for item in os.scandir(realpath):

                link_ok = True

                if item.is_symlink():
                    destlink = self.readAndConvertLink(item.path, realpath)
                    (link_ok, fullname2) = self.path_is_good(destlink)

                #
                #   Don't include symlinks that lead out of the sandboxed areas
                #

                if link_ok:
                    #
                    #   Don't show things other than files and/or directories
                    #
                    if item.is_dir() or item.is_file():

                        # Seperate with NULs
                        if buff != b"":
                            buff.append(0)

                        buff += item.name

                        # Cache the results for later stat() requests
                        self.stat_cache[item.path] = (self.curr_time, item.stat())

            self.__server_send_data_response(buff)

        return still_ok

#
#----------------------------------------------------------------------
#

    def server_handle_list_cmd(self, path):
        (still_ok, realpath) = self.path_is_good(path)

        if still_ok:
            if os.path.isfile(realpath):
                # Single file?  Just send back TWO NULs

                self.__server_send_data_response(b"\0\0")

            elif os.path.isdir(realpath):
                still_ok = self.__server_handle_list_dir(realpath)

            else:
                # Don't admit to having anything other than
                #   files and directories

                still_ok = 0

        if not still_ok:
            self.server_send_err_response()

        return still_ok

#
# ----------------------------------------------------------------------
#

    def server_handle_get_file(self, path):
        (is_good, realpath) = self.path_is_good(path)

        # Only handle files (nothting else)
        if is_good and os.path.isfile(realpath):
            still_ok = self.server_send_data_from_file(realpath)
        else:
            self.server_send_err_response()
            still_ok = 0

        return still_ok
#
# ----------------------------------------------------------------------
#

    #
    # (is_dir, mode, size, mtime, ctime)
    #
    # mtime and ctime are truncated to whole seconds only
    #
    def server_handle_stat_cmd(self, path):
        still_ok = 1

        (is_good, realpath) = self.path_is_good(path)

        if is_good:
            initialpath = self.path_convert_aliases(path)
            result = self.stat_file_helper(realpath, initialpath)

            if result is not None:
                (flags, mode, size, mtime, ctime) = result

                is_dir = flags & 0x01
                is_file = flags & 0x02

                if is_file or is_dir:
                    buff = self.stat_struct.pack(flags, mode, size,
                                                 mtime, ctime)

                    still_ok = self.__server_send_data_response(buff)

            else:
                still_ok = 0
                self.server_send_err_response()

        else:
            still_ok = 0
            self.server_send_err_response()

        return still_ok

    def server_handle_symlink_cmd(self, path):
        unaliased_path = self.path_convert_aliases(path)
        (is_good, realpath) = self.path_is_good(path)

        still_ok = 1

        if is_good:
            result = b""

            if os.path.islink(unaliased_path):
                curr_dir = os.path.dirname(unaliased_path)
                destpath = self.readAndConvertLink(unaliased_path, curr_dir)

                # Verify that the destination is also a good path
                (is_also_good, realdestpath) = self.path_is_good(destpath)

                if is_also_good:
                    if os.path.isdir(realpath):
                        base = realpath
                    else:
                        base = os.path.dirname(realpath)

                    relpath = os.path.relpath(realdestpath, base)

                    result = relpath
                else:
                    self.print_debug(4, "Destination of symlink",
                                     realpath, "is not in a good directory")
                    still_ok = 0
        else:
            still_ok = 0

        # Send the resulting path if valid
        #  (send an error response otherwise)
        if still_ok:
            still_ok = self.__server_send_data_response(result)

        else:
            self.server_send_err_response()

        return still_ok

# ----------------------------------------------------------------------
#

    def server_handle_hash_file(self, path):
        result = None
        (is_good, realpath) = self.path_is_good(path)

        # Only handle files (nothing else)
        if is_good and os.path.isfile(realpath):
            result = self.compute_hash(realpath)

        if result is not None:
            still_ok = self.__server_send_data_response(result.encode('latin1'))

        else:
            self.server_send_err_response()
            still_ok = 0

        return still_ok
#
# ----------------------------------------------------------------------
#

    #
    # (is_dir, mode, size, mtime, ctime)

#
# ----------------------------------------------------------------------
#

    def server_get_cmd_and_respond(self):

        self.print_debug(3, "Waiting for a command")

        (cmd, data) = self.server_get_cmd_full_path_or_id()

        if cmd is None:
            pass            # Already handled

        elif cmd == "C":
            self.print_debug(3, "CMD=C - Send Continuation Data")

            # Send the next portion of the buffer
            self.__server_send_next_buffer_block(data)

        elif cmd == "G":
            self.print_debug(3, "CMD=G - Get File")

            self.server_handle_get_file(data)

        elif cmd == "H":
            self.print_debug(3, "CMD=H - Hash File")

            self.server_handle_hash_file(data)

        elif cmd == "K":
            self.print_debug(3, "CMD=K - Return SymlinK")

            self.server_handle_symlink_cmd(data)

        elif cmd == "L":
            self.print_debug(3, "CMD=L - List Directory")

            self.server_handle_list_cmd(data)

        elif cmd == "M":
            self.print_debug(3, "CMD=M - Get MaxPacket")

            self.__server_send_data_response(self.max_packet.to_bytes(4, 'little'))

        elif cmd == "N":
            self.print_debug(3, "CMD=N - No Op")

            self.__server_send_data_response()     # Empty data response

        elif cmd == "Q":
            self.print_debug(3, "CMD=Q - SetPriority")

            # This is handled by a relay - not implemented by the server

            self.__server_send_data_response()     # Empty data response

        elif cmd == "S":
            self.print_debug(3, "CMD=S - Stat a File/Directory")

            self.server_handle_stat_cmd(data)

        elif cmd == "Z":
            self.print_debug(3, "CMD=Z - Reset Buffers")

            self.__reset_buffers()                  # Empty all buffers
            self.__server_send_data_response()     # Empty data response
