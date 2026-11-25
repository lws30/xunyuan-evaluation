"""Read robot states from MuJoCo for recording and scoring."""

import itertools
import math


class MuJoCoSampler:
    def __init__(self, model, *, root_body, terrain_geom_names,
                 allowed_terrain_body_names, boundary_check):
        import mujoco
        import numpy as np
        self.mj, self.np, self.model = mujoco, np, model
        self.root = model.body(root_body).id
        self.boundary_check = boundary_check
        if not callable(boundary_check):
            raise ValueError("A scene-side full-envelope boundary checker is required")
        self.terrain = {model.geom(name).id for name in terrain_geom_names}
        self.allowed = {model.body(name).id for name in allowed_terrain_body_names}
        if not self.terrain or not self.allowed:
            raise ValueError("Declare terrain geoms and allowed contact bodies explicitly")
        bodies = {self.root}
        for i in range(model.nbody):
            parent = i
            while parent:
                if parent == self.root:
                    bodies.add(i)
                    break
                parent = int(model.body_parentid[parent])
        self.robot_geoms = {i for i in range(model.ngeom) if int(model.geom_bodyid[i]) in bodies
                            and (model.geom_contype[i] or model.geom_conaffinity[i])}
        if not self.robot_geoms or not self.allowed <= bodies:
            raise ValueError("Invalid robot collision/contact configuration")

    def sample(self, data, *, action_valid, intervention=False):
        """Call after kinematics/contact updates at every physics step, including t=0."""
        m, np = self.model, self.np
        velocity = np.zeros(6)
        self.mj.mj_objectVelocity(m, data, self.mj.mjtObj.mjOBJ_BODY, self.root, velocity, 0)
        rotation = data.xmat[self.root].reshape(3, 3)
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
        roll = math.atan2(rotation[2, 1], rotation[2, 2])
        pitch = math.asin(float(np.clip(-rotation[2, 0], -1, 1)))
        points = []
        for gid in sorted(self.robot_geoms):
            centre, half = m.geom_aabb[gid, :3], m.geom_aabb[gid, 3:]
            matrix = data.geom_xmat[gid].reshape(3, 3)
            for signs in itertools.product([-1, 1], repeat=3):
                local = centre + half * np.asarray(signs)
                points.append((data.geom_xpos[gid] + matrix @ local).tolist())
        forbidden = 0
        for contact in data.contact:
            a, b = int(contact.geom1), int(contact.geom2)
            if a not in self.robot_geoms and b not in self.robot_geoms:
                continue
            robot, other = (a, b) if a in self.robot_geoms else (b, a)
            allowed = other in self.terrain and int(m.geom_bodyid[robot]) in self.allowed
            forbidden += int(not allowed)
        return {"time_s": float(data.time), "position_m": data.xpos[self.root].tolist(),
                "yaw_rad": yaw, "roll_rad": roll, "pitch_rad": pitch,
                "speed_mps": float(np.linalg.norm(velocity[3:5])), "yaw_rate_rps": float(velocity[2]),
                "envelope_points_m": points, "forbidden_contacts": forbidden,
                "out_of_bounds": bool(self.boundary_check(points)),
                "action_valid": action_valid, "intervention": intervention}
