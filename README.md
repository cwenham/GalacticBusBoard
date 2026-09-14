# Pimoroni Galactic Unicorn Bus Arrival Board for the UK

   * Near-live updates using TransportAPI
   * Displays route number, final stop, and estimated arrival time in minutes with colourised text for easy reading
   * Configure the A, B, C and D buttons to switch between up to four different stops
   * Scrolls up through the list of departures with configurable speed
   * Responds to the brightness control buttons
   * Auto-dims brightness with the Unicorn's built-in light sensor
   * Goes into non-refreshing sleep mode with the "Zzz" button, to save on API quotas
   * Countdown to next refresh displayed as a line that shifts from green to red
   * Configurable operating hours to economise on API quota, especially if you're using TransportAPI's free plan
   * All configuration in `config.py`
   * Set up custom abbreviations for bus stops in `destinations.csv`

Use [the UK Dept. for Transportation site](https://naptan.api.dft.gov.uk) or your local bus company's web site to find the ATCO code for the bus stops you want to monitor. These should be available for all bus stops in the UK. Pick up to four and edit the `BUS_STOPS` list in `config.py` to map them to the A,B,C and D buttons.

While you're editing the config file, you should also set your Wifi SSID and password, plus a TransportAPI App ID and Key that you can get by signing up at [TransportAPI](https://developer.transportapi.com).

Upload all files to the Galactic Unicorn board with Thonny or other method. Restart and it should start connecting to your WiFi and fetch the first updates for the first bus stop.
