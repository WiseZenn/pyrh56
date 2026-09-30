"""
RH56 servo control register address map (checked against user manual V1.09).

All 16-bit data is **little-endian** (low byte first).
"""

# ==================================================================
#  Basic parameters
# ==================================================================
REG_HAND_ID = 1000
REG_BAUD_RATE = 1002
REG_CLEAR_ERROR = 1004
REG_SAVE = 1005
REG_RESET_PARA = 1006
REG_GESTURE_NO_SET = 1008         # Legacy alias; reserved in V1.09, not used by this SDK
REG_GESTURE_FORCE_CLB = 1009

# ==================================================================
#  Default parameters (saved to Flash)
# ==================================================================
REG_CURRENT_LIMIT = 1020          # 6 short, 12 bytes
REG_DEFAULT_SPEED_SET = 1032      # 6 short, 12 bytes
REG_DEFAULT_FORCE_SET = 1044      # 6 short, 12 bytes
REG_USER_DEF_ANGLE = 1066         # Legacy constant; not documented in V1.09, not used

# ==================================================================
#  Runtime command registers
# ==================================================================
REG_VOLTAGE = 1472                # 1 short, read-only

REG_POS_SET = 1474                # 6 short, 12 bytes, range 0-2000
REG_ANGLE_SET = 1486              # 6 short, 12 bytes, -1 or 0-1000
REG_FORCE_SET = 1498              # 6 short, 12 bytes, range 0-1000
REG_SPEED_SET = 1522              # 6 short, 12 bytes, range 0-1000

# ==================================================================
#  Runtime feedback registers (read-only)
# ==================================================================
REG_POS_ACT = 1534                # Actuator actual position, 6 short, 12 bytes, 0-2000
REG_ANGLE_ACT = 1546              # Angle actual value, 6 short, 12 bytes, 0-1000
REG_FORCE_ACT = 1582              # Actual force, 6 signed short, 12 bytes, grams
REG_CURRENT = 1594                # Current, 6 short, 12 bytes, mA
REG_ERROR = 1606                  # Error code, 6 bytes
REG_STATUS = 1612                 # Status code, 6 bytes
REG_TEMP = 1618                   # Temperature, 6 bytes, degC

# ==================================================================
#  Backward-compatible aliases
# ==================================================================
REG_TARGET_POSITION = REG_ANGLE_SET
REG_TARGET_FORCE = REG_FORCE_SET
REG_TARGET_SPEED = REG_SPEED_SET
REG_FORCE_THRESHOLD = REG_FORCE_SET

REG_ACTUAL_POSITION = REG_POS_ACT      # Deprecated - use REG_ANGLE_ACT
REG_ACTUAL_ANGLE = REG_ANGLE_ACT
REG_ACTUAL_FORCE = REG_FORCE_ACT

# ==================================================================
#  Status code map
# ==================================================================
STATUS_TEXT = {
    0: "Releasing",
    1: "Grasping",
    2: "Position reached",
    3: "Force control reached",
    5: "Overcurrent protection",
    6: "Actuator stall",
    7: "Actuator fault",
}

# ==================================================================
#  Error bit definitions
# ==================================================================
ERROR_BITS = {
    0: "Stall fault",
    1: "Over-temperature fault",
    2: "Overcurrent fault",
    3: "Motor anomaly",
    4: "Communication fault",
}
