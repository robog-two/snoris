import os
import time
from cmath import isnan
from functools import reduce
import json

version = 1.0

temp_sensors = []
fans = []

window = 10 # 1 second to measure fan variation

print(f"Snoris Setup v{version} 💤")
print("This script may need root permissions to set fan values.\n")

def ds(a, b):
    return abs(a - b)

def readInline(path: str) -> str:
    content = ""
    with open(path, "r") as f:
        content = f.read()
    return content

def writeInline(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)

def changeFan(pwm_path, rpm_path, three_sem, rpm_measurements, speed):
    i = 0
    writeInline(pwm_path, str(speed))
    while True:  # wait for fan to stabilize according to our data
        i += 1
        time.sleep(0.1)
        rpm_measurements.append(int(readInline(rpm_path)))
        rpm_measurements.pop(0)
        if round(max(rpm_measurements) - min(rpm_measurements), 2) <= three_sem and i > window:
            # Break if the range is within 99% of fan variation
            break

def main():
    print("🌡 Step 1: Collecting Temperature Sensors (try lm_sensors if these are missing items)")

    for device in os.listdir("/sys/class/hwmon"):
        try:
            print(f" - Found device " + readInline("/sys/class/hwmon/" + device + '/name').split("\n")[0])
            for sensor in os.listdir("/sys/class/hwmon/" + device):
                if sensor.startswith("temp") and sensor.endswith("_input"):
                    # This is a temperature sensor!
                    measured_temp = int(readInline(f"/sys/class/hwmon/{device}/{sensor}")) / 1000
                    print(f"   - Sensor at {sensor} reads {measured_temp} °C")
                    temp_sensors.append({
                        "path": f"/sys/class/hwmon/{device}/{sensor}",
                        "baseline": measured_temp,
                    })
        except OSError:
            print(f" - Skipping {device}, could not read.")

    print("\n🌬️ Step 2: Calibrating fans")

    for device in os.listdir("/sys/class/hwmon"):
        try:
            print(f" - Found device " + readInline("/sys/class/hwmon/" + device + '/name').split("\n")[0])

            pwm_path = f"/sys/class/hwmon/{device}/pwm1"
            rpm_path = f"/sys/class/hwmon/{device}/fan1_input"

            has_pwm = os.path.exists(pwm_path)
            has_rpm = os.path.exists(rpm_path)

            if has_pwm and has_rpm:
                print("   - It's a fan! Setting speed to maximum & waiting 60s to stabilize")
                writeInline(pwm_path, "255")
                time.sleep(int(os.getenv("SNORIS_FAN_WAIT", "60")))

                rpm_measurements = []
                print("   - Measuring fan variability")
                for i in range(100):
                    current_rpm = int(readInline(rpm_path))
                    if not isnan(current_rpm) and current_rpm > 0:
                        rpm_measurements.append(current_rpm)
                    time.sleep(0.1)
                if len(rpm_measurements) == 0:
                    raise OSError("Not a fan.")
                rpm_range = ((max(rpm_measurements) - min(rpm_measurements)) + 5) * 2
                print(f"   - {rpm_range} normal RPM variation (2 * range)")
                rpm_measurements = rpm_measurements[window:] # for testing variation later on

                print(f"   - Going to lowest setting")
                changeFan(pwm_path, rpm_path, rpm_range, rpm_measurements, 0)

                lowest_rpms = int(readInline(rpm_path))
                print(f"     - Lowest setting is {lowest_rpms}RPM")

                print(f"   - Going to highest setting")
                spin_up_start = time.time()
                changeFan(pwm_path, rpm_path, rpm_range, rpm_measurements, 255)
                spin_up_time = round(time.time() - spin_up_start, 2) - (window / 10)
                highest_rpms = int(readInline(rpm_path))

                print(f"     - Fan took {spin_up_time}s to spin up, reached {highest_rpms}RPM")

                print("   - Checking intermediate speeds")
                all_speeds = [lowest_rpms, highest_rpms]
                all_pwms = []
                for i in range(1, 5):
                    pwm_value = i * 50
                    writeInline(pwm_path, str(pwm_value))
                    time.sleep(spin_up_time)
                    current_rpm = int(readInline(rpm_path))
                    is_new = reduce(lambda acc, el: ds(el, current_rpm) > rpm_range and acc, all_speeds, True)
                    if is_new:
                        print(f"     - Found new speed {pwm_value} spins at {current_rpm}RPM")
                        all_speeds.append(current_rpm)
                        all_pwms.append(pwm_value)
                fans.append({
                    "pwm_path": pwm_path,
                    "rpm_path": rpm_path,
                    "rpm_range": rpm_range,
                    "valid_pwm_settings": [0, *all_pwms , 255],
                })
        except OSError:
            print(f" - Skipping {device}, could not read.")

    os.makedirs("/etc/snoris/", exist_ok=True)
    with open("/etc/snoris/snoris_calibration.json", "w") as calibration_file:
        json.dump({
            "temp_sensors": temp_sensors,
            "fans": fans,
        }, calibration_file)
        print("📬 Wrote to calibration file")


if __name__ == "__main__":
    main()
