"""LiDAR observations and the actual ground-contact friction used by MuJoCo."""

import math


LIDAR = {'channels': 16, 'azimuth_samples': 128, 'vertical_degrees': [-15, 15],
         'horizontal_degrees': 360, 'minimum_range_m': .08, 'maximum_range_m': 20,
         'frequency_hz': 10, 'position_in_base_m': [.2, 0, .25],
         'frame': 'lidar: x forward, y left, z up', 'columns': ['x_m', 'y_m', 'z_m']}

FRONT_CAMERA = {'shape': [144, 256, 3], 'dtype': 'uint8', 'color': 'RGB', 'frequency_hz': 10,
    'fov_y_degrees': 70, 'position_in_base_m': [.28, 0, .12],
    'intrinsics_px': {'fx': 72 / math.tan(math.radians(35)), 'fy': 72 / math.tan(math.radians(35)), 'cx': 128, 'cy': 72},
    'frame': 'camera: x right, y down, z forward',
    'axes_in_base': {'x': [0, -1, 0], 'y': [0, 0, -1], 'z': [1, 0, 0]}}


def set_ground_friction(model, coefficient):
    """Assign both sides so geom mixing cannot mask a low-friction ground."""
    import numpy as np
    if isinstance(coefficient, bool) or not math.isfinite(coefficient) or coefficient <= 0:
        raise ValueError('摩擦系数必须大于 0')
    floor = model.geom('floor').id
    ids = np.where((model.geom_contype != 0) | (model.geom_conaffinity != 0))[0]
    model.geom_friction[ids, 0] = coefficient
    model.geom_friction[floor, 0] = coefficient
    if model.npair:
        model.pair_friction[:, :2] = coefficient


def contact_friction(model, data):
    """Read coefficients from active contacts, rather than the XML defaults."""
    floor = model.geom('floor').id
    return [float(c.friction[0]) for c in data.contact
            if floor in (int(c.geom1), int(c.geom2)) and c.efc_address >= 0]


class Lidar:
    def __init__(self, model):
        import numpy as np
        self.model = model
        self.base = model.body('base_link').id
        azimuth = np.linspace(-math.pi, math.pi, LIDAR['azimuth_samples'], endpoint=False)
        elevation = np.deg2rad(np.linspace(*LIDAR['vertical_degrees'], LIDAR['channels']))
        az, el = np.meshgrid(azimuth, elevation)
        self.directions = np.stack((np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)), axis=-1).reshape(-1, 3)
        self.offset = np.array(LIDAR['position_in_base_m'])
        # World geometry is group 0. Robot visual/collision geoms use 2/1.
        self.groups = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)

    def scan(self, data):
        import mujoco
        import numpy as np
        rotation = data.xmat[self.base].reshape(3, 3)
        origin = data.xpos[self.base] + rotation @ self.offset
        world = self.directions @ rotation.T
        ids = np.full(len(world), -1, dtype=np.int32)
        distances = np.full(len(world), -1., dtype=np.float64)
        kwargs = dict(geomgroup=self.groups, flg_static=True, bodyexclude=-1,
                      geomid=ids, dist=distances, nray=len(world), cutoff=LIDAR['maximum_range_m'])
        try:
            mujoco.mj_multiRay(self.model, data, origin, world.ravel(), normal=None, **kwargs)
        except TypeError:
            mujoco.mj_multiRay(self.model, data, origin, world.ravel(), **kwargs)
        valid = ((distances >= LIDAR['minimum_range_m']) &
                 (distances <= LIDAR['maximum_range_m']) & (ids >= 0))
        return (self.directions[valid] * distances[valid, None]).astype(np.float32)
