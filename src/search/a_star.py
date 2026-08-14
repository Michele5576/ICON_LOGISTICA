"""
A* search algorithm on the road graph of Bari for vehicle routing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math
import heapq
import pickle
from typing import Optional, Tuple, List, Dict, Set

from src.config import V_MAX_KMH, VELOCITA_KMH, GRAFO_PICKLE, KB_DIR, DEPOSITO_LAT, DEPOSITO_LON

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on Earth in km."""
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def a_star(
    start: str, goal: str,
    adj: dict, coords: dict,
    evita_ztl: bool = False,
    ztl_set: set = None
) -> Tuple[Optional[List[str]], float, float]:
    """
    Returns (path, total_distance_km, total_time_hours) or (None, inf, inf).
    """
    if ztl_set is None:
        ztl_set = set()

    if start not in coords or goal not in coords:
        return None, float('inf'), float('inf')

    # Priority queue stores (f_score, node)
    open_set = []
    heapq.heappush(open_set, (0.0, start))
    
    came_from = {}
    g_score = {start: 0.0} # time in hours
    distance_score = {start: 0.0} # distance in km

    def h(node: str) -> float:
        """Admissible heuristic: straight line distance / max speed (gives min time)"""
        lat1, lon1 = coords[node]
        lat2, lon2 = coords[goal]
        dist = haversine(lat1, lon1, lat2, lon2)
        return dist / V_MAX_KMH

    while open_set:
        current_f, current = heapq.heappop(open_set)

        if current == goal:
            # Reconstruct path
            path = []
            curr = current
            while curr in came_from:
                path.append(curr)
                curr = came_from[curr]
            path.append(start)
            path.reverse()
            return path, distance_score[current], g_score[current]

        # In case we have a stale entry in the heap
        if current_f > g_score[current] + h(current):
            continue

        for neighbor, distance_km, road_type in adj.get(current, []):
            if evita_ztl and neighbor in ztl_set and neighbor != goal and neighbor != start:
                continue

            speed = VELOCITA_KMH.get(road_type, VELOCITA_KMH.get('default', 30.0))
            edge_time = distance_km / speed
            tentative_g = g_score[current] + edge_time

            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                distance_score[neighbor] = distance_score[current] + distance_km
                f_score = tentative_g + h(neighbor)
                heapq.heappush(open_set, (f_score, neighbor))

    return None, float('inf'), float('inf')

def carica_grafo() -> Tuple[Dict, Dict, Set]:
    """Load adj, coords, ztl_set from files."""
    with open(GRAFO_PICKLE, 'rb') as f:
        data = pickle.load(f)
    adj = data['adj']
    coords = data['coords']
    
    ztl_set = set()
    ztl_path = KB_DIR / 'ztl_nodi.pl'
    if ztl_path.exists():
        with open(ztl_path, encoding='utf-8') as f:
            for line in f:
                if line.startswith('in_ztl('):
                    nid = line.strip().replace('in_ztl(', '').replace(').', '')
                    ztl_set.add(nid)
    else:
        print(f"[WARNING] ZTL file not found at {ztl_path}")

    return adj, coords, ztl_set

def trova_nodo_vicino(lat: float, lon: float, coords: Dict[str, Tuple[float, float]]) -> str:
    """Find nearest graph node to given coordinates."""
    nearest = None
    min_dist = float('inf')
    for node, (n_lat, n_lon) in coords.items():
        dist = haversine(lat, lon, n_lat, n_lon)
        if dist < min_dist:
            min_dist = dist
            nearest = node
    return nearest

def main():
    print("[INFO] Loading graph...")
    adj, coords, ztl_set = carica_grafo()
    print(f"[OK] Graph loaded: {len(coords)} nodes, {sum(len(v) for v in adj.values())} edges.")
    print(f"[INFO] Nodes in ZTL: {len(ztl_set)}")

    # Find deposito node
    deposito_node = trova_nodo_vicino(DEPOSITO_LAT, DEPOSITO_LON, coords)
    print(f"[INFO] Deposito node: {deposito_node} (lat, lon = {coords[deposito_node]})")

    # Pick a client node
    client_lat, client_lon = None, None
    client_path = KB_DIR / 'clienti.pl'
    if client_path.exists():
        with open(client_path, encoding='utf-8') as f:
            for line in f:
                if line.startswith('cliente('):
                    # cliente(c1, 41.123, 16.85, ...).
                    parts = line.split(',')
                    try:
                        client_lat = float(parts[1].strip())
                        client_lon = float(parts[2].strip())
                        break
                    except ValueError:
                        continue
    
    if client_lat is not None and client_lon is not None:
        client_node = trova_nodo_vicino(client_lat, client_lon, coords)
    else:
        # Fallback to some node
        client_node = list(coords.keys())[-1]
    
    print(f"[INFO] Client node: {client_node} (lat, lon = {coords[client_node]})")

    print("[INFO] Running A* WITHOUT ZTL avoidance...")
    path1, dist1, time1 = a_star(deposito_node, client_node, adj, coords, evita_ztl=False, ztl_set=ztl_set)
    if path1:
        print(f"[OK] Found path without ZTL avoidance: {len(path1)} nodes, {dist1:.2f} km, {time1:.2f} hours")
    else:
        print("[ERROR] Path without ZTL not found.")

    print("[INFO] Running A* WITH ZTL avoidance...")
    path2, dist2, time2 = a_star(deposito_node, client_node, adj, coords, evita_ztl=True, ztl_set=ztl_set)
    if path2:
        print(f"[OK] Found path with ZTL avoidance: {len(path2)} nodes, {dist2:.2f} km, {time2:.2f} hours")
    else:
        print("[ERROR] Path with ZTL not found. (Could be unreachable without entering ZTL)")

    if path1 and path2:
        if dist2 > dist1 or time2 > time1:
            print("[INFO] Comparison: Avoiding ZTL takes longer/further as expected.")
        else:
            print("[INFO] Comparison: ZTL avoidance doesn't impact distance/time significantly for this route.")

if __name__ == '__main__':
    main()
