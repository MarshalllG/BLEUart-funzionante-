# script to implement a BLE Uart Peripheral

# - Environmental data extraction (or simulation)
# - Estabilish a BLE connection
# - Notify the Central by sending the current state
# - Receive commands from the Central

_MY_NAME = "ID000001"

import bluetooth # BLE native library for uPython
from ble_advertising import advertising_payload # for the advertising frames
from binascii import hexlify # data conversion lib
import pyb

# constants for the BLE UART service
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

# definition of UART service with two characteristics, RX and TX

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX = (
	bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"),
	_FLAG_NOTIFY, 
)
_UART_RX = (
	bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
	_FLAG_WRITE,  
)
_UART_SERVICE = (
	_UART_UUID,
	(_UART_TX, _UART_RX),
)

# max bytes for messages
_MAX_NB_BYTES = const(128)

class BLEperipheral:

	# initialization
	def __init__(self, ble, name=_MY_NAME, charbuf=_MAX_NB_BYTES):
		self._ble = ble
		self._ble.active(True)
		self._ble.irq(self._irq)
		self._ble.config(mtu=_MAX_NB_BYTES)

		# service registration
		((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_UART_SERVICE,))
		
		# preparing buffers
		self._ble.gatts_set_buffer(self._tx_handle, charbuf, True)
		self._ble.gatts_set_buffer(self._rx_handle, charbuf, True)
		
		self._ble.gatts_write(self._tx_handle, bytes(charbuf))
		self._ble.gatts_write(self._rx_handle, bytes(charbuf))
		
		self._connections = set()
		self._rx_buffer = bytearray()
		self._handler = None

		# advertising
		self._payload = advertising_payload(name=name, services=[_UART_UUID])
		self._advertise()
		
		# view the MAC addr
		dummy, byte_mac = self._ble.config('mac')
		hex_mac = hexlify(byte_mac) 
		print("My MAC addr : %s" %hex_mac.decode("ascii"))

	# interrupt to manage receptions
	def irq(self, handler):
		self._handler = handler

	# monitor connections to send notifications
	def _irq(self, event, data):

		# if a central connects
		if event == _IRQ_CENTRAL_CONNECT:
			conn_handle, _, _ = data
			self._connections.add(conn_handle)
			print("New connection", conn_handle)

		# if a central disconnects
		elif event == _IRQ_CENTRAL_DISCONNECT:
			conn_handle, _, _ = data
			print("Disconnected", conn_handle)
			if conn_handle in self._connections:
				self._connections.remove(conn_handle)
			# restarts advertising to allow new connections
			self._advertise()

		# when a client writes to a characteristic exposed by the server
		# (management of reception events from the central)
		elif event == _IRQ_GATTS_WRITE:
			conn_handle, value_handle = data
			if conn_handle in self._connections and value_handle == self._rx_handle:
				self._rx_buffer += self._ble.gatts_read(self._rx_handle)
				if self._handler:
					self._handler()

		# payload size change event
		elif event == _IRQ_MTU_EXCHANGED:
			print("The maximum message size is now " + str(_MAX_NB_BYTES) + " bytes")

	# check if there are messages waiting to be read in RX
	def any(self):
		return len(self._rx_buffer)

	# print characters received in RX
	def read(self, sz=None):
		if not sz:
			sz = len(self._rx_buffer)
		result = self._rx_buffer[0:sz]
		self._rx_buffer = self._rx_buffer[sz:]
		return result

	# writes in TX a message to the attention of the central
	def write(self, data):
		for conn_handle in self._connections:
			self._ble.gatts_notify(conn_handle, self._tx_handle, data)

	# close the connection
	def close(self):
		for conn_handle in self._connections:
			self._ble.gap_disconnect(conn_handle)
		self._connections.clear()

	# to start advertising, specify that a Central can connect to the device
	def _advertise(self, interval_us=500000):
		self._ble.gap_advertise(interval_us, adv_data=self._payload, connectable = True)

	# is the device connected to a central
	def is_connected(self):
		return len(self._connections) > 0


# function to manage the led state
def change_led_state(lux): # we consider 50 lux as the threshold
	led1 = pyb.LED(3)
	if lux < 50:
		led1.on() # turn ON the LED
		if lux < 10:
			led1.intensity(255)  # intensity ranges between 0 (off) and 255 (full on)
		elif lux >= 10 and lux < 20:
			led1.intensity(180) 
		elif lux >= 20 and lux < 30:
			led1.intensity(120) 
		elif lux >= 30 and lux < 40:
			led1.intensity(60) 
		return True
	elif lux >= 40:
		led1.off() # turn OFF the LED
		return False
	else: 
		print("ERROR, unknown value read")


###### MAIN PROGRAM ######
def demo():
	
	print("BLE peripheral : %s" %_MY_NAME) 

	import time # to introduce delays

	print("Misure simulate")
	import random # to generate psueudo-random values

	# BLE instantiation
	ble = bluetooth.BLE()
	uart = BLEperipheral(ble)

	# handler for rx event
	def on_rx():
		message = uart.read().decode().strip()
		print("data received from Central : ", message)
		if (message = "change LED state"):
			if(pyb.LED(3).on()):
				pyb.LED(3).off()
				print("Central command received: turning LED off")
			else:
				pyb.LED(3).on("Central command received: turning LED ON")

	# asynchronous rx of data
	uart.irq(handler=on_rx)

	# simulate_task
	try:
		led_state = False # OFF

		while True:

			temp = random.randint(-1, 50)  # random value (°C)
			humi = random.randint(0, 100) # random value (%)
			illum = random.randint(0, 200) # random value (lux)

			new_state = change_led_state(illum)

			# conversions to strings
			s_temp = str(temp)
			s_humi = str(humi)
			s_illum = str(illum)

			# visualization on the serial port of the USB USER
			print("temperature : " + s_temp + " °C, humidity : " + s_humi + " %, illuminance : " + s_illum + " lux")

			if uart.is_connected():

				# data concatenation
				data = s_temp + "|" + s_humi + "|" + s_illum

				# tx to Central
				uart.write(data)

				print("data sent to Central : " + data)

				# if the light state changes, inform the Central
				if (led_state != new_state):
					if (new_state):
						data = "New state of Peripheral %s, LED was turned ON" %_MY_NAME
					else:
						data = "New state of Peripheral %s, LED was turned OFF" %_MY_NAME
					uart.write(data)
					led_state = new_state

				print("data sent to Central : " + data)

			# temporization: 5 seconds
			time.sleep_ms(5000)

	# error handler
	except KeyboardInterrupt:
		pass 

	# close connection
	uart.close()

if __name__ == "__main__":
	demo()
