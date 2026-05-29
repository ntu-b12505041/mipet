from gpiozero import DigitalOutputDevice, Motor
from time import sleep

# TB6612 wiring:
# Motor A: AIN1=GPIO17, AIN2=GPIO27, PWMA=GPIO18
# Motor B: BIN1=GPIO23, BIN2=GPIO24, PWMB=GPIO13
# STBY=GPIO22

standby = DigitalOutputDevice(22)
motor_a = Motor(forward=17, backward=27, enable=18)
motor_b = Motor(forward=23, backward=24, enable=13)


def stop_all():
    motor_a.stop()
    motor_b.stop()


try:
    standby.on()

    print("Both motors forward")
    motor_a.forward(0.5)
    motor_b.forward(0.5)
    sleep(2)

    print("Stop")
    stop_all()
    sleep(1)

    print("Both motors backward")
    motor_a.backward(0.5)
    motor_b.backward(0.5)
    sleep(2)

    print("Stop")
    stop_all()
    sleep(1)

    print("Turn test: A forward, B backward")
    motor_a.forward(0.5)
    motor_b.backward(0.5)
    sleep(2)

finally:
    stop_all()
    standby.off()
