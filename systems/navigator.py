import os
import json
import math
import networkx as nx

# --- Configuration ---
NETWORK_FILE = "../assets/region_network.json"


class Navigator:
    """
    A stateful navigator that provides step-by-step guidance with heading constraints.
    """

    def __init__(self, network_file_path: str):
        """Initializes the navigator by loading the map."""
        print(f"Loading navigation network from {network_file_path}...")
        self._region_data = self._load_region_data(network_file_path)
        self._network = self._build_networkx_graph()
        if not self._network:
            raise IOError(f"Failed to build a valid graph from {network_file_path}")

        self.goal_region = None
        self.current_path = []
        print("Navigator ready.")

    def set_destination(self, goal_region: str):
        """Sets the final destination for the navigator."""
        if goal_region not in self._network:
            print(f"Error: Goal region '{goal_region}' not found in network.")
            self.goal_region = None
            self.current_path = []
        else:
            print(f"New destination set: {goal_region}")
            self.goal_region = goal_region
            self.current_path = []  # Clear old path, a new one will be calculated

    def update(self, current_region: str, imu_heading_deg: float):
        """
        Primary update loop. Takes current location and heading, returns guidance.
        """
        if not self.goal_region:
            return {"status": "IDLE", "message": "Destination not set."}
        if current_region not in self._network:
            return {"status": "ERROR", "message": f"Invalid current region '{current_region}'."}
        if current_region == self.goal_region:
            return {"status": "GOAL_REACHED", "direction_vector": [0.0, 0.0]}

        world_heading_deg = self._convert_imu_to_world_yaw(imu_heading_deg)

        # Re-plan if we have no path or we've strayed from the current one
        if not self.current_path or current_region not in self.current_path:
            self._plan_new_path(current_region, world_heading_deg)

        # If after planning we still have no path, we must turn around
        if not self.current_path:
            return {"status": "TURN_AROUND", "direction_vector": [0.0, 0.0]}

        # Find the next waypoint on our stored path
        try:
            current_index = self.current_path.index(current_region)
            next_region = self.current_path[current_index + 1]
        except (ValueError, IndexError):
            # This can happen if we overshoot the second to last node
            self._plan_new_path(current_region, world_heading_deg)
            if not self.current_path:
                return {"status": "TURN_AROUND", "direction_vector": [0.0, 0.0]}
            next_region = self.current_path[1]

        # Provide guidance towards the next waypoint
        required_heading_deg = self._calculate_angle_to_neighbor(current_region, next_region)
        direction_vec = self._get_direction_vector(required_heading_deg)

        return {
            "status": "NAVIGATING",
            "direction_vector": direction_vec,
            "next_region": next_region,
            "full_path": self.current_path
        }

    def _plan_new_path(self, current_region: str, car_heading_deg: float):
        """Internal method to find the best forward-facing path and store it."""
        candidates = []
        for neighbor in self._network.neighbors(current_region):
            required_heading = self._calculate_angle_to_neighbor(current_region, neighbor)
            turn_angle = self._calculate_turn_angle(car_heading_deg, required_heading)

            if turn_angle > 135:
                continue

            try:
                path_len = nx.shortest_path_length(self._network, source=neighbor, target=self.goal_region)
                candidates.append((1 + path_len, neighbor))
            except nx.NetworkXNoPath:
                continue

        if not candidates:
            self.current_path = []  # No valid forward path found
            return

        # Select the neighbor that leads to the shortest overall path
        _, best_next_region = min(candidates, key=lambda x: x[0])
        self.current_path = nx.shortest_path(self._network, source=current_region, target=self.goal_region,
                                             weight='weight')

        # A final check to ensure our chosen next step is on the new A* path
        if len(self.current_path) < 2 or self.current_path[1] != best_next_region:
            self.current_path = [current_region] + nx.shortest_path(self._network, source=best_next_region,
                                                                    target=self.goal_region)

    # --- Private Helper Methods ---

    def _load_region_data(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Network file not found at: {file_path}")
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data.get('regions', data)

    def _build_networkx_graph(self):
        G = nx.Graph()
        for name, data in self._region_data.items():
            pos = data.get('position')
            if pos and isinstance(pos, list) and len(pos) >= 2:
                G.add_node(name, pos=pos[:2])
        for name, data in self._region_data.items():
            if name in G:
                for neighbor in data.get('neighbors', []):
                    if neighbor in G: G.add_edge(name, neighbor, weight=1)
        return G

    def _convert_imu_to_world_yaw(self, imu_yaw_deg: float) -> float:
        return (imu_yaw_deg - 90 + 360) % 360

    def _calculate_angle_to_neighbor(self, start_node, end_node):
        x1, y1 = self._network.nodes[start_node]['pos']
        x2, y2 = self._network.nodes[end_node]['pos']
        return (math.degrees(math.atan2(y2 - y1, x2 - x1)) + 360) % 360

    def _calculate_turn_angle(self, current_heading, target_heading):
        diff = abs(current_heading - target_heading)
        return min(diff, 360 - diff)

    def _get_direction_vector(self, angle_deg: float) -> list[float]:
        angle_rad = math.radians(angle_deg)
        # Vector is [North, East] which corresponds to [sin, cos] of a standard angle
        north_comp = math.sin(angle_rad)
        east_comp = math.cos(angle_rad)
        return [north_comp, east_comp]


# --- Example Usage ---
def run_example():
    """Demonstrates how to use the new Navigator class."""
    navigator = Navigator(NETWORK_FILE)

    # 1. Set the destination
    goal_region_num = input("Enter your GOAL region number (e.g., 26): ").strip()
    navigator.set_destination(f"r_{goal_region_num.zfill(2)}")

    # 2. Start the main loop
    while True:
        print("-" * 30)
        # Get simulated inputs from user
        current_num = input("VPR location number? ('quit' to exit): ").strip()
        if current_num.lower() == 'quit': break
        imu_heading_str = input(f"  -> IMU heading for r_{current_num.zfill(2)} (degrees)?: ").strip()

        try:
            current_region = f"r_{current_num.zfill(2)}"
            imu_heading = float(imu_heading_str)
        except ValueError:
            print("Invalid input.")
            continue

        # 3. Get guidance from the navigator
        guidance = navigator.update(current_region, imu_heading)

        # 4. Interpret the result
        status = guidance.get("status")
        print(f"\nSTATUS: {status}")

        if status == "NAVIGATING":
            vector = guidance['direction_vector']
            print(f"  -> Direction Vector: [N: {vector[0]:+.2f}, E: {vector[1]:+.2f}]")
            print(f"  -> Next region on path: {guidance['next_region']}")
        elif status in ["GOAL_REACHED", "TURN_AROUND", "ERROR"]:
            if "message" in guidance: print(f"  -> {guidance['message']}")
            if status == "GOAL_REACHED": break  # End simulation


if __name__ == '__main__':
    run_example()