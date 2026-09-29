# Fixture for test_no_param_literals: lines 4, 5 and 6 must be reported, the others not.
# ruff: noqa
x = 0 + 1 + 2  # exempt
clearance = 10  # violation (int)
clearance_f = 10.0  # violation (float equals int default)
hem = -50  # violation (negative)
ok = 10  # param-ok: fixture shows the escape
not_a_default = 11
pair = 2  # exempt even though features = 2
