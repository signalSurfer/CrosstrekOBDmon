<h1>Crosstrek OBD Monitor</h1>  
This is a script to be autorun on a raspberry pi 4b with a 7x11 inch screen.  
The script enumerates and connects to a usb-obd elm 327 interface and polls stats from the ECU.
</br></br>
The polled information is shown in a continuously updated tkinter UI as a grid of gauges labeled with what the gauge is displaying, and the related value.
</br></br>
the script should also turn the screen yellow and scroll any DTC codes across the screen should they be present.
</br></br>
V1.0 WIP
