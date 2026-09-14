# Pimoroni Galactic Unicorn Bus Arrival Board for the UK

This is for the [Pimoroni Galactic Unicorn LED matrix display](https://shop.pimoroni.com/products/space-unicorns?variant=40842033561683). It has not been designed for, or tested with the Stellar or Cosmic Unicorn varieties.

   * Near-live updates using TransportAPI
   * Displays route number, final stop, and estimated arrival time in minutes with colourised text for easy reading
   * Configure the A, B, C and D buttons to switch between up to four different stops
   * Scrolls up through the list of departures with configurable speed
   * Responds to the brightness control buttons
   * Auto-dims brightness with the Unicorn's built-in light sensor
   * Goes into non-refreshing sleep mode with the "Zzz" button, to save on API usage
   * Countdown to next refresh displayed as a line that shifts from green to red
   * Configurable operating hours to economise on API usage, especially if you're using TransportAPI's free plan. Program will automatically compute the shortest interval between calls that still fits within your plan.
   * All configuration in `config.py`
   * Set up custom abbreviations for bus stops in `destinations.csv`

Use [the UK Dept. for Transportation site](https://naptan.api.dft.gov.uk) or your local bus company's web site to find the ATCO code for the bus stops you want to monitor. These should be available for all bus stops in the UK. Pick up to four and edit the `BUS_STOPS` list in `config.py` to map them to the A,B,C and D buttons.

While you're editing the config file, you should also set your Wifi SSID and password, plus a TransportAPI App ID and Key that you can get by signing up at [TransportAPI](https://developer.transportapi.com). Their free plan allows for 30 calls per day, so set the operating hours to when you'd actually use it so it can refresh more often (computed automatically). If you pick one of their paid plans, you can adjust the config to poll more often and keep your board updated as close to realtime as you can.

Upload all files to the Galactic Unicorn board with Thonny or other method. Restart and it should start connecting to your WiFi and fetch the first updates for the first bus stop.

`destinations.csv` is a comma-separated file with an ID column, the text of the bus stop as it appears in the TransportAPI feed, and the abbreviation you'd like to use in the display. This is useful for stops with long names, or names that shorten to the same abbreviation. If the stop isn't found in this file, the program will automatically truncate the name to fit the available space.

You can maintain this lookup table in a database or spreadsheet as long as you can export it to CSV and upload it to the board.
