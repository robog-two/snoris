import json
import time
from math import degrees, floor

version = 1.0

config = None

def readInline(path: str) -> str:
    content = ""
    with open(path, "r") as f:
        content = f.read()
    return content

def writeInline(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)

def highestRelativeTemp() -> int:
    highest = 0
    for sensor in config["temp_sensors"]:
        current_temp = int(readInline(sensor["path"]))
        relative_temp = current_temp - sensor["baseline"]
        if relative_temp > highest:
            highest = relative_temp
    return highest

def main():
    print(f"Snoris Fan Controller Daemon v{version} 💤")

    with open("/etc/snoris/config.json", "r") as config_file:
        config = json.load(config_file)

    if config is None:
        print("⛔️ Config not found! You MUST run snoris_setup first!")
        exit(1)

    settings = config["user_options"]

    lowest_number_of_steps = 256 # how many different fan speeds are supported
    for fan in config["fan_calibration"]:
        if len(fan["pwm_to_rpm"]) < lowest_number_of_steps:
            lowest_number_of_steps = len(fan["pwm_to_rpm"])

    # Let's say our fan supports three speeds: 0, 150, and 255
    # and degrees_til_max_fan is 40
    # The step map should be:
    # [ (5, 1), (40, -1) ]
    # which means that 5 degrees above baseline, we will use medium speed
    # then above 40 degrees we will use the maximum speed
    step_map = []
    if settings["degrees_til_max_fan"] > 5 and lowest_number_of_steps > 2:
        degrees_above = 5
        for i in range(1, lowest_number_of_steps - 1):
            step_map.append((floor(degrees_above), i))
            degrees_above += (settings["degrees_til_max_fan"] - 5) / (lowest_number_of_steps - 2)

    step_map.append((settings["degrees_til_max_fan"], -1))

    print("Fan \"curve\", each tuple is (temp above baseline, fan speed")
    print(step_map)

    current_setting = None
    while True:
        try:
            new_setting = None
            highest_relative_temp = highestRelativeTemp()
            if highest_relative_temp < step_map[0][0]:
                new_setting = 0
            else:
                i = 0
                while new_setting is None:
                    if highest_relative_temp > step_map[i][0]:
                        new_setting = step_map[i][1]
                    i += 1

            # TODO: should also check fan RPM to make sure they are reaching targets and not dead
            if current_setting is None or new_setting != current_setting:
                current_setting = new_setting
                print(f"🌡️ Temperature at {highest_relative_temp}. Changing fans to setting {current_setting} (remember, -1 = max speed)")
                for fan in config["fan_calibration"]:
                    pwm_to_set = fan["pwm_to_rpm"][current_setting]["pwm"]
                    writeInline(fan["pwm_path"], pwm_to_set)
            time.sleep(5)
        except Exception as e:
            print("Couldn't update fan speeds due to error:", e)
            print("This may result in an overheat!")


if __name__ == "__main__":
    main()