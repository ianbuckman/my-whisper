# Runtime hook: mock scipy and numba so mlx_whisper.timing can import
# We don't use the timing/alignment feature, so mocks are fine
import types
import sys

# Mock scipy
scipy = types.ModuleType('scipy')
scipy.signal = types.ModuleType('scipy.signal')
sys.modules['scipy'] = scipy
sys.modules['scipy.signal'] = scipy.signal

# Mock numba
numba = types.ModuleType('numba')
numba.jit = lambda *a, **kw: (lambda f: f)  # no-op decorator
sys.modules['numba'] = numba
