import json
import time
from math import degrees, floor

version = 1.0

def readInline(path: str) -> str:
    content = ""
    with open(path, "r") as f:
        content = f.read()
    return content

def writeInline(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)

def highestRelativeTemp() -> int:
    # TODO: implement
    return 0

def main():
    print(f"Snoris Fan Controller Daemon v{version} 💤")

    config = None
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

    # Above degrees_til_max_fan, go to the highest speed (index -1 = last item in list of speeds)
    step_map = []
    if settings["degrees_til_max_fan"] > 5 and lowest_number_of_steps > 2:
        degrees_above = 5
        # Let's say our fan supports three speeds: 0, 150, and 255
        # and degrees_til_max_fan is 40
        # The step map should be:
        # [ (5, 1), (40, -1) ]
        # which means that 5 degrees above baseline, we will use medium speed
        # then above 40 degrees we will use the maximum speed
        for i in range(1, lowest_number_of_steps - 1):
            step_map.append((floor(degrees_above), i))
            degrees_above += (settings["degrees_til_max_fan"] - 5) / (lowest_number_of_steps - 2)

    step_map.append((settings["degrees_til_max_fan"], -1))

    print(step_map)

    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()