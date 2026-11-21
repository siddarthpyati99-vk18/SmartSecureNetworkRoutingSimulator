# Network Routing Simulator — Python / Flask

This is the Python migration of the supplied Spring Boot project. The original HTML, CSS and JavaScript frontend is retained and served by Flask. The Java backend has been replaced with Flask API routes and Python routing logic.

## Features migrated

- Network topology builder and existing frontend visualizations
- Dijkstra, BFS, Bellman-Ford, A* and Floyd-Warshall route endpoints
- Traffic-aware edge costs, disabled links and failed-node handling
- Route metrics and decision explanation
- Algorithm comparison
- Network analytics and health score
- Monitoring and dynamic rerouting event log
- Demo scenario catalogue and scenario data endpoint
- Save/load/delete networks and routing history
- SQLite by default; optional MySQL connection

## Requirements

- Python 3.10+
- pip

## Windows setup (VS Code terminal / PowerShell)

```powershell
cd path\to\network-routing-flask
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\\Scripts\\activate.bat
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Database

The project runs with SQLite automatically and creates `routing_simulator.db` on first launch. No database installation is required for the first demo.

To use MySQL instead, create a database (for example `routing_db`), set the environment variable `DATABASE_URL` before starting Flask, and use a connection string such as:

```text
mysql+pymysql://USERNAME:PASSWORD@localhost:3306/routing_db
```

Keep credentials in a local `.env` or environment variables; do not commit passwords. `.env.example` contains a safe template.

PowerShell example:

```powershell
$env:DATABASE_URL = "mysql+pymysql://USERNAME:PASSWORD@localhost:3306/routing_db"
python app.py
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/routing/shortest-path` | Calculate a route |
| POST | `/api/routing/compare` | Compare five algorithms |
| POST | `/api/routing/analytics` | Network analytics |
| POST | `/api/routing/monitor` | One monitoring / rerouting cycle |
| GET | `/api/routing/reroute-events` | Rerouting event history |
| GET | `/api/routing/scenarios` | Scenario list |
| GET | `/api/routing/scenarios/<id>` | Full scenario payload |
| POST | `/api/networks` | Save a graph |
| GET | `/api/networks` | List saved graphs |
| GET | `/api/networks/<id>` | Load a graph |
| DELETE | `/api/networks/<id>` | Delete a graph |
| GET | `/api/networks/history` | Routing history |
| DELETE | `/api/networks/history` | Clear routing history |
| GET | `/api/health` | Health check |

## Example route request

```json
{
  "nodes": ["A", "B", "C"],
  "edges": [
    {"source": "A", "destination": "B", "weight": 4, "latency": 5, "capacity": 100, "trafficLevel": "LOW"},
    {"source": "B", "destination": "C", "weight": 3, "latency": 6, "capacity": 100, "trafficLevel": "LOW"},
    {"source": "A", "destination": "C", "weight": 10, "latency": 2, "capacity": 100, "trafficLevel": "LOW"}
  ],
  "source": "A",
  "destination": "C",
  "algorithm": "DIJKSTRA",
  "directed": true,
  "useTraffic": false,
  "failedNodes": [],
  "failedEdges": []
}
```

## Migration notes

- Frontend assets are copied unchanged from the supplied Java project.
- The original Java project used MySQL. The migrated version defaults to SQLite so it can run locally without extra setup; MySQL remains configurable.
- A* uses a zero heuristic in this first Python port, preserving optimal route correctness while behaving like Dijkstra. This can be upgraded to a non-zero admissible heuristic after validating the coordinate/topology model.
- The frontend scenario selector uses the original scenario catalogue; full scenario payloads are available at `/api/routing/scenarios/<id>`.
- Verify the algorithm behavior against your original Java application before using it for final project evaluation.
