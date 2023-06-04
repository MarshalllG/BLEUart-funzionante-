# This script implements a BLE Uart Central

# 1 - Detect a BLE Peripheral
# 2 - Estabilish a BLE connection
# 3 - Send commands to the Peripheral
_TARGET_PERIPHERAL_NAME = "ID000001"
_NBCHAR = const(8)

import bluetooth # BLE lib
from ble_advertising import decode_services, decode_name # to decode received msg
from binascii import hexlify
import ubinascii
import pyb
import machine
import time

# Address types (cf. https://docs.micropython.org/en/latest/library/ubluetooth.html)
ADDR_TYPE_PUBLIC = const(0x00)
ADDR_TYPE_RANDOM = const(0x01)

# Time constants (T_WAIT: ms / others: s)
_T_WAIT  = const(100)

# known peripherals' MAC addresses 
peripherals = [ 
    bytes(b'\x02\x05\x82\x06\x35\x9e'),
	bytes(b'\x02\x04\x88\x16\x32\xee')]

# constants for BLE service
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_advertising_payload_CONNECT = const(7)
_IRQ_advertising_payload_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_WRITE_DONE = const(17)
_IRQ_GATTC_NOTIFY = const(18)
_IRQ_MTU_EXCHANGED = const(21)

# connectable devices
_ADV_IND = const(0x00)
_ADV_DIRECT_IND = const(0x01)

# parameters for scanning cycle
_SCAN_DURATION_MS = const(30000)
_SCAN_INTERVAL_US = const(30000)
_SCAN_WINDOW_US = const(30000)

# definition of Uart services
_UART_SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_RX_CHAR_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX_CHAR_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

# global variables
MAC_address = 0 # Central's MAC addr
Central_ACK_required = 0 # ack or not

# max bytes for messages
_MAX_NB_BYTES = const(128)

# Class to generate the BLE Central
class BLECentral:

    # initialization
    def __init__(self, ble):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._ble.config(mtu=_MAX_NB_BYTES)
        self._reset()
        
        # to view the MAC addr
        dummy, byte_mac = self._ble.config('mac')
        hex_mac = hexlify(byte_mac)
        print("My MAC addr : %s" %hex_mac.decode("ascii"))

    # reset
    def _reset(self):
        
        # empty cache
        self._name = None
        self._addr_type = None
        self._addr = None
        
        # callbacks
        self._scan_callback = None
        self._conn_callback = None
        self._read_callback = None

        self._notify_callback = None

        # addresses and characteristics of the connected Peripheral
        self._conn_handle = None
        self._start_handle = None
        self._end_handle = None
        self._tx_handle = None
        self._rx_handle = None

    # handling interrupts event
    def _irq(self, event, data):

        # event: scanned device
        if event == _IRQ_SCAN_RESULT:
        
            # read the content of advertising frames
            addr_type, addr, adv_type, rssi, adv_data = data

            # if the advertising reports a device offering a Uart service
            if adv_type in (_ADV_IND, _ADV_DIRECT_IND) and _UART_SERVICE_UUID in decode_services(adv_data):
            
                # if this is the Peripheral device, reference it and stop scanning
                self._name = decode_name(adv_data) or "?"
                if self._name[0:_NBCHAR] == _TARGET_PERIPHERAL_NAME[0:_NBCHAR]:
                    self._addr_type = addr_type
                    self._addr = bytes(addr) # Note: le tampon addr a pour propriétaire l'appelant, donc il faut le copier.
                    self._name = decode_name(adv_data) or "?"
                    self._ble.gap_scan(None)

        # event: scan terminated
        elif event == _IRQ_SCAN_DONE:
            if self._scan_callback:
                if self._addr:
                    # the Peripheral has been detected
                    self._scan_callback(self._addr_type, self._addr, self._name)
                    self._scan_callback = None
                    print("Scan terminated, success : Peripheral %s found" %_TARGET_PERIPHERAL_NAME)
                else:
                    # the scan exceeded its "time-out" period before to find Peripheral device
                    self._scan_callback(None, None, None)
                    print("Scan terminated, failure : %s didn't found Peripheral %s s" %(_TARGET_PERIPHERAL_NAME,_SCAN_DURATION_MS/1000))

        # event: connection estabilished
        elif event == _IRQ_advertising_payload_CONNECT:
            conn_handle, addr_type, addr = data
            if addr_type == self._addr_type and addr == self._addr:
                self._conn_handle = conn_handle
                self._ble.gattc_exchange_mtu(self._conn_handle)
                self._ble.gattc_discover_services(self._conn_handle)
            b = bytes(addr)
            print("Connected with peripheral %s" %hexlify(b).decode("ascii"))


        # event: disconnection
        elif event == _IRQ_advertising_payload_DISCONNECT:
            conn_handle, addr_type, addr = data
            if conn_handle == self._conn_handle:
                self._reset()
            print("Disconnected from Peripheral with MAC addr {}...".format(hexlify(addr)))   


        # event: service notified from Peripheral to Central
        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            if conn_handle == self._conn_handle and uuid == _UART_SERVICE_UUID:
                self._start_handle, self._end_handle = start_handle, end_handle

        # event: search of services terminated
        elif event == _IRQ_GATTC_SERVICE_DONE:
            if self._start_handle and self._end_handle:
                self._ble.gattc_discover_characteristics(
                    self._conn_handle, self._start_handle, self._end_handle
                )
            else:
                print("Uart service is unreachable.")

        # event: characteristic notified from Peripheral to Central
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, properties, uuid = data
            if conn_handle == self._conn_handle and uuid == _UART_RX_CHAR_UUID:
                self._rx_handle = value_handle
            if conn_handle == self._conn_handle and uuid == _UART_TX_CHAR_UUID:
                self._tx_handle = value_handle

        # event: search of characteristics terminated
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            if self._tx_handle is not None and self._rx_handle is not None:
                if self._conn_callback:
                    self._conn_callback()
            else:
                print("Uart characteristic RX not discoverable.")

        # event: device acknowledgment
        elif event == _IRQ_GATTC_WRITE_DONE:
            conn_handle, value_handle, status = data
            print("writing in RX done")

        # event: device notification response
        elif event == _IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            if conn_handle == self._conn_handle and value_handle == self._tx_handle:
                if self._notify_callback:
                    self._notify_callback(notify_data)

        # event: payload size changed
        elif event == _IRQ_MTU_EXCHANGED:
            print("The maximum message size is now " + str(_MAX_NB_BYTES) + " bytes")

    # returns true if there is a connection to the Uart service
    def is_connected(self):
        return (
            self._conn_handle is not None
            and self._tx_handle is not None
            and self._rx_handle is not None
        )

    def scan(self, callback=None):
        """
        Find all available devices.

        See https://docs.micropython.org/en/latest/library/ubluetooth.html for gap_scan() parameters.

        Parameters:
            callback (function): callback to be invoked in _IRQ_SCAN_DONE if the desired device
                                 was found in _IRQ_SCAN_RESULT
        """
        self._addr_type = None
        self._addr = None
        self._scan_callback = callback
        try:
            self._ble.gap_scan(2000, 30000, 30000, True)
        except OSError:
            pass

    def connect(self, addr_type=None, addr=None, callback=None):
        """
        Connect to the specified device (otherwise use cached address from a scan).

        See https://docs.micropython.org/en/latest/library/ubluetooth.html for connect().

        Parameters:
            addr_type (int):     address type (PUBLIC or RANDOM)
            addr (bytes):        BLE MAC address
            callback (function): callback to be invoked in _IRQ_PERIPHERAL_CONNECT
            
        Returns:
            bool: True  if valid address type and address was available and connect() was called without error
                        (not connected yet!),
                False otherwise
        """
        if not(addr_type is None) and not(addr is None):
            # if provided, use address type and address provided as parameters
            # (otherwise use address type and address from preceeding scan)
            self._addr_type = addr_type
            self._addr = addr
        self._conn_callback = callback
        if self._addr_type is None or self._addr is None:
            return False
        try:
            self._ble.gap_connect(self._addr_type, self._addr)
        except OSError:
            pass
        return True

        
    def disconnect(self):
        """
        Disconnect from current device and reset object's attributes.
        """
        if not self._conn_handle:
            return
        try:
            self._ble.gap_disconnect(self._conn_handle)
            print("Disconnected success!")
        except OSError:
            pass
        self._reset()

    def wait_for_connection(self, status, timeout_ms):
        """
        Wait until connection reaches 'status' or a timeout occurrs.

        The connection status is polled in _T_WAIT intervals.

        Parameters:
            status (bool):     expected connection status
            timeout_ms (int) : timeout in ms

        Returns:
            bool: True  desired status occurred,
                  False timeout ocurred.
        """
        t0 = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            time.sleep_ms(_T_WAIT)
        return False

    # send data to Uart
    # this method allows the Central to send a message to the Peripheral
    def write(self, v, response = False):
        
        if not self.is_connected():
            return

        self._ble.gattc_write(self._conn_handle, self._rx_handle, v, 1 if response else 0)
        
        # confirm that the ack has been sent
        global Central_ACK_required
        Central_ACK_required = 0

    # enable receive event handler on Uart
    def on_notify(self, callback):
        self._notify_callback = callback

# receive event handler that responds to a notification
def on_receipt(v):
    
    global MAC_address
    
    # conversion to bytes
    b = bytes(v)

    # convert the received bytes into characters coded in UTF-8 format
    payload = b.decode('utf-8')

    print("received message from Peripheral with MAC addr " + str(MAC_address) + " : ", payload)

    global Central_ACK_required
    Central_ACK_required = 1

# instantiating a BLE Central
ble = bluetooth.BLE()
central = BLECentral(ble)


########### MAIN PROGRAM ###########
def demo():

    while True:
        
        for addr in peripherals:
            central.search_addr    = addr

            print("Searching for device with MAC address {}...".format(hexlify(addr)))
            
            central.scan()
            print("Trying to connect to device with MAC address {}...".format(hexlify(addr)))
            
            conn_result = central.connect(ADDR_TYPE_PUBLIC, addr)
            print("connect() = ", conn_result)
            
            # capture receive events
            central.on_notify(on_receipt)

            while central.wait_for_connection(False, 15000):

                global Central_ACK_required
            
                if Central_ACK_required == 1:
                    try:
                        v = "ack from Central " + MAC_address
                        central.write(v)
                    except:
                        print("Failed to send response from Central")

                # when button SW1 is pressed on Central board, force the change of the LED state on the Peripheral board
                # sw1 = pyb.Pin('SW1', pyb.Pin.IN)
                # sw1.init(pyb.Pin.IN, pyb.Pin.PULL_UP, af=-1)
                # current_sw1 = 1
                # sw1_value = sw1.value()
                # if sw1_value != current_sw1:
                #     if sw1_value == 0: # user button SW1 is pressed
                #         command = "change LED state"
                #         try:
                #             central.write(command)
                #             print("sending command: change LED state")
                #         except:
                #             print("Failed to send command")
                #     current_sw1 = sw1_value       

            central.disconnect()

            if central.wait_for_connection(False, 3000):
                print("Disconnected")
            else:
                print("Disconnect failed (timeout)!")
                central._reset()
            
        print("end of the polling cycle : sleeping 20s")
        time.sleep(20)

if __name__ == "__main__":
    demo()
