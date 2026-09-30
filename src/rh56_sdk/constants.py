# ------------------------------------------------------------------
#  Default open/close presets in device coordinates
# ------------------------------------------------------------------
RH56_OPEN_FRAME = [1000, 1000, 1000, 1000, 1000, 900]
RH56_CLOSE_FRAME = [0, 0, 0, 0, 0, 900]

SERVO_COUNT = 6
SERVO_MIN = 0
SERVO_MAX = 1000

# ------------------------------------------------------------------
#  Finger indices
# ------------------------------------------------------------------
RH56_PINKY_INDEX = 0
RH56_RING_INDEX = 1
RH56_MIDDLE_INDEX = 2
RH56_INDEX_INDEX = 3
RH56_THUMB_FLEX_INDEX = 4
RH56_THUMB_ROT_INDEX = 5

# ------------------------------------------------------------------
#  Thumb-specific limits
# ------------------------------------------------------------------
RH56_THUMB_FLEX_CLOSE_LIMIT = 0
RH56_THUMB_FLEX_OPEN_LIMIT = 1000
RH56_THUMB_FLEX_FACTORY_OPEN_LIMIT = 1000
RH56_THUMB_ROT_SAFE = 900

# ------------------------------------------------------------------
#  Protocol defaults
# ------------------------------------------------------------------
DEFAULT_NODE_ID = 1
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 0.1
