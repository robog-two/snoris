import json
import os
import platform
import statistics
import time
from cmath import isnan
from functools import reduce

version = 1.0 # be sure to update this in other files. Can't be extracted since they need to be independent of each other.

temp_sensors = []
fan_calibration = []
user_options = {}

measurements_in_window = 10  # 1 second to measure fan variation


def ds(a, b):
    return abs(a - b)


def readInline(path: str) -> str:
    content = ""
    with open(path, "r") as f:
        content = f.read()
    return content


def writeInline(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(str(content))


def pwm_rpm_tuple(pwm, rpm):
    return {
        "pwm": pwm,
        "expected_rpm": rpm,
    }


def changeFan(pwm_path, rpm_path, rpm_range, rpm_measurements, speed):
    i = 0
    writeInline(pwm_path, str(speed))
    while True:  # wait for fan to stabilize according to our data
        i += 1
        time.sleep(0.1)
        rpm_measurements.append(int(readInline(rpm_path)))
        rpm_measurements.pop(0)
        avg_rpm = statistics.mean(rpm_measurements)
        # If the lowest and highest values are less than rpm_range from the mean,
        # Then this fan is at a stable speed. (if we have actually measured enough data)
        if ds(min(rpm_measurements), avg_rpm) < rpm_range and ds(max(rpm_measurements),
                                                                 avg_rpm) < rpm_range and i >= measurements_in_window:
            break
    return round(statistics.mean(rpm_measurements))


def main():
    print(f"Snoris Setup v{version} 💤")

    # Check for priveleges and that we are on a Linux system - not good to write to these files on a Mac!
    if platform.system() != "Linux":
        print("⛔️ Snoris is a fan controller for Linux systems only.")
        exit(1)

    if os.geteuid() != 0:
        print("⛔️ Snoris needs root priveleges. It uses this to do the following:")
        print(" - Change fan speeds by writing to PWM device files in /sys for calibration")
        print(" - Install systemd services that manage fan speeds based on temperature")
        print("If you are unsure whether Snoris is safe to run on your system, feel free to")
        print("check the source code yourself. Please submit any concerns as GitHub issues/PRs.")
        exit(1)

    print("\nYour system should not be under heavy load so we can get a baseline temperature.")
    if not input("Is now a good time to read a baseline temperature? [y/N]").lower().startswith("y"):
        print("⛔️ User reports not ready to read a baseline temperature.")
        exit(0)

    print("\n🌡 Collecting Temperature Sensors (try lm_sensors if these are missing items)")

    for device in os.listdir("/sys/class/hwmon"):
        try:
            print(f" - Found device " + readInline("/sys/class/hwmon/" + device + '/name').split("\n")[0])
            for sensor in os.listdir("/sys/class/hwmon/" + device):
                if sensor.startswith("temp") and sensor.endswith("_input"):
                    # This is a temperature sensor!
                    measured_temp = round(int(readInline(f"/sys/class/hwmon/{device}/{sensor}")) / 1000)
                    if measured_temp <= 0:
                        print(
                            f"   - ⚠️ Sensor {sensor} reads freezing so is likely misconfigured. Ignoring this sensor.")
                    else:
                        print(f"   - Sensor at {sensor} reads {measured_temp}°C")
                        temp_sensors.append({
                            "path": f"/sys/class/hwmon/{device}/{sensor}",
                            "baseline": measured_temp,
                        })
        except OSError:
            print(f" - Skipping {device}, could not read.")

    hottest_temp = max(list(map(lambda it: it["baseline"], temp_sensors)))
    print(f"\nYour highest baseline temperature was {hottest_temp}°C")
    value = round(int(input(
        "How many degrees may the temperature *increase* before Snoris sets fans to their maximum speed? [30]") or 30))
    print(f"OK. For example, fans will be highest when this component reaches {hottest_temp + value}°C")
    user_options["degrees_til_max_fan"] = value

    user_options["install_automatically"] = True
    if (input("\nDo you want Snoris to setup its system services automatically (works best for most users)? [Y/n]")
            .lower()
            .startswith("n")):
        print("OK. Snoris will not mess with your systemd configuration.")
        user_options["install_automatically"] = False

    if user_options["install_automatically"]:
        print("\nThe fan calibration process requires no interaction and will take a few minutes.")
        time.sleep(5)

    print("\n🌬️ Calibrating fans")

    for device in os.listdir("/sys/class/hwmon"):
        try:
            print(f" - Found device " + readInline("/sys/class/hwmon/" + device + '/name').split("\n")[0])

            pwm_path = f"/sys/class/hwmon/{device}/pwm1"
            rpm_path = f"/sys/class/hwmon/{device}/fan1_input"

            has_pwm = os.path.exists(pwm_path)
            has_rpm = os.path.exists(rpm_path)

            pwm_to_rpm = []

            if has_pwm and has_rpm:
                wait_time = int(os.getenv("SNORIS_FAN_WAIT", "60"))
                print(f"   - It's a fan! Setting speed to maximum & waiting {wait_time}s to stabilize")
                writeInline(pwm_path, "255")
                time.sleep(wait_time)

                rpm_measurements = []
                print("   - Measuring fan variability")
                for i in range(100):
                    current_rpm = int(readInline(rpm_path))
                    if not isnan(current_rpm) and current_rpm > 0:
                        rpm_measurements.append(current_rpm)
                    time.sleep(0.1)
                if len(rpm_measurements) == 0:
                    print(
                        "   - ⚠️ Trouble calibrating fan. Make sure you have proper kernel modules. Try using lm_sensors to fix.")
                    raise OSError("Not a fan.")
                rpm_range = ((max(rpm_measurements) - min(rpm_measurements)) + 5) * 2
                print(f"   - {rpm_range} normal RPM variation (2 * range)")
                rpm_measurements = rpm_measurements[measurements_in_window:]  # for testing variation later on

                current_rpm = int(readInline(rpm_path))
                pwm_to_rpm.append(pwm_rpm_tuple(255, current_rpm))
                print(f"   - Highest setting is {current_rpm}RPM")

                print(f"   - Going to lowest setting")
                current_rpm = changeFan(pwm_path, rpm_path, rpm_range, rpm_measurements, 0)
                pwm_to_rpm.append(pwm_rpm_tuple(0, current_rpm))
                print(f"     - Lowest setting is {current_rpm}RPM")

                print("   - Checking intermediate speeds")
                for i in range(1, 5):
                    # Change fan to this PWM value
                    pwm_value = i * 50
                    current_rpm = changeFan(pwm_path, rpm_path, rpm_range, rpm_measurements, pwm_value)

                    is_new = reduce(lambda acc, el: ds(el["expected_rpm"], current_rpm) > rpm_range and acc, pwm_to_rpm,
                                    True)
                    if is_new:
                        print(f"     - Found new speed {pwm_value} spins at {current_rpm}RPM")
                        pwm_to_rpm.append(pwm_rpm_tuple(pwm_value, current_rpm))

                pwm_to_rpm.sort(key=lambda dict: dict["pwm"])  # sort by slowest to highest settings
                fan_calibration.append({
                    "pwm_path": pwm_path,
                    "rpm_path": rpm_path,
                    "rpm_range": rpm_range,
                    "pwm_to_rpm": pwm_to_rpm,
                })
        except OSError:
            print(f" - ⚠️ Skipping {device}, could not read.")

    if len(fan_calibration) == 0:
        print("⛔️ Aborting setup. No fans calibrated successfully. Snoris will not do anything on your system.")
    if len(temp_sensors) == 0:
        print("⛔️ Aborting setup. No temperature sensors were found. Snoris will not do anything on your system.")

    save_path = "./config.json"
    if user_options["install_automatically"]:
        os.makedirs("/etc/snoris/", exist_ok=True)
        save_path = "/etc/snoris/config.json"

    with open(save_path, "w") as calibration_file:
        json.dump({
            "config_version": version,
            "user_options": user_options,
            "temp_sensors": temp_sensors,
            "fan_calibration": fan_calibration,
        }, calibration_file, indent=4)
        print("\n📬 Configuration saved!")


if __name__ == "__main__":
    main()
