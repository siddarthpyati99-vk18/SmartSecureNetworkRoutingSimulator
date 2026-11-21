from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from pathlib import Path
import os
import math

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'routing_simulator.db'}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class SavedNetwork(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    directed = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    nodes_json = db.Column(db.Text, nullable=False, default="[]")
    edges_json = db.Column(db.Text, nullable=False, default="[]")

class RoutingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80))
    destination = db.Column(db.String(80))
    algorithm = db.Column(db.String(40))
    path = db.Column(db.Text)
    cost = db.Column(db.Integer, default=0)
    hops = db.Column(db.Integer, default=0)
    execution_time_ms = db.Column(db.Float, default=0)
    condition = db.Column(db.String(60), default="Normal")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/<path:filename>")
def frontend_files(filename):
    candidate = BASE_DIR / "static" / filename
    if candidate.is_file():
        return send_from_directory(app.static_folder, filename)
    return jsonify({"error": "Not found"}), 404

def edge_cost(edge, use_traffic):
    weight = int(edge.get("weight", 1))
    if not use_traffic:
        return weight
    level = str(edge.get("trafficLevel", "LOW")).upper()
    penalty = math.floor(weight * (0.8 if level == "HIGH" else 0.3) + 0.5) if level in ("HIGH", "MEDIUM") else 0
    return weight + penalty + max(0, int(edge.get("latency", 0)))

def graph_data(data):
    nodes = list(dict.fromkeys(map(str, data.get("nodes") or [])))
    edges = data.get("edges") or []
    failed_nodes = set(map(str, data.get("failedNodes") or []))
    failed_edges = set(data.get("failedEdges") or [])
    directed = data.get("directed", True)
    alive = set(nodes)
    for e in edges:
        alive.update((str(e.get("source")), str(e.get("destination"))))
    alive -= failed_nodes
    adjacency = {n: [] for n in alive}
    valid_edges = []
    for e in edges:
        u, v = str(e.get("source")), str(e.get("destination"))
        if u not in alive or v not in alive or e.get("disabled", False):
            continue
        if f"{u}->{v}" in failed_edges or (not directed and f"{v}->{u}" in failed_edges):
            continue
        item = dict(e, source=u, destination=v)
        adjacency[u].append((v, item))
        valid_edges.append(item)
        if not directed:
            rev = dict(item, source=v, destination=u)
            adjacency[v].append((u, rev))
    return alive, adjacency, valid_edges

def route_result(data, algorithm=None):
    started = datetime.now()
    algo = (algorithm or data.get("algorithm") or "DIJKSTRA").upper()
    source, target = str(data.get("source") or ""), str(data.get("destination") or "")
    alive, adj, edges = graph_data(data)
    empty = dict(found=False, algorithm=algo, source=source, destination=target,
                 path=[], cost=0, hops=0, executionTimeMs=0, message="",
                 visitedNodes=0, animation=[])
    if source not in alive or target not in alive:
        empty["message"] = "Source or destination node is unavailable."
        return empty
    if source == target:
        empty.update(found=True, path=[source], message="Route found.", metrics={
            "totalLatencyMs": 0, "bottleneckCapacity": 0, "averageCapacity": 0,
            "trafficLevel": "LOW", "linkCount": 0
        })
        return empty

    use_traffic = bool(data.get("useTraffic", False))
    inf = float("inf")
    dist = {n: inf for n in alive}
    prev = {}
    dist[source] = 0
    visited = []
    animation = []

    def snapshot(step, current=None, frontier=None, relaxed=None, message=""):
        animation.append({
            "stepNumber": step, "currentNode": current,
            "visited": list(visited), "frontier": list(frontier or []),
            "relaxedEdges": list(relaxed or []),
            "distances": {k: (int(v) if v != inf else 2147483647) for k, v in dist.items()},
            "message": message
        })

    if algo in ("DIJKSTRA", "A_STAR"):
        import heapq
        heuristic = {n: 0 for n in alive}
        if algo == "A_STAR":
            # Match the Java implementation: admissible hop-count heuristic
            # multiplied by the minimum positive edge cost.
            reverse = {n: [] for n in alive}
            costs = []
            for u, links in adj.items():
                for v, e in links:
                    reverse.setdefault(v, []).append(u)
                    costs.append(max(edge_cost(e, use_traffic), 1))
            min_edge = min(costs, default=1)
            from collections import deque
            hops_to_target = {target: 0}
            queue = deque([target])
            while queue:
                v = queue.popleft()
                for u in reverse.get(v, []):
                    if u not in hops_to_target:
                        hops_to_target[u] = hops_to_target[v] + 1
                        queue.append(u)
            heuristic = {n: hops_to_target.get(n, 0) * min_edge for n in alive}
        heap = [(heuristic.get(source, 0), source)]
        step = 1
        while heap:
            priority, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.append(u)
            relaxed, frontier = [], []
            for v, e in adj.get(u, []):
                candidate = dist[u] + edge_cost(e, use_traffic)
                if candidate < dist[v]:
                    dist[v] = candidate
                    prev[v] = u
                    relaxed.append(f"{u}->{v}")
                    heapq.heappush(heap, (candidate + heuristic.get(v, 0), v))
                if v not in visited:
                    frontier.append(v)
            snapshot(step, u, frontier, relaxed, f"Expanding {u} using {algo.replace('_',' ')}.")
            step += 1
            if u == target:
                break
    elif algo == "BFS":
        from collections import deque
        q = deque([source]); seen = {source}; step = 1
        while q:
            u = q.popleft(); visited.append(u); frontier=[]; relaxed=[]
            for v, e in adj.get(u, []):
                if v not in seen:
                    seen.add(v); q.append(v); prev[v]=u
                    dist[v] = dist[u] + edge_cost(e, use_traffic)
                    relaxed.append(f"{u}->{v}")
                if v not in visited: frontier.append(v)
            snapshot(step, u, frontier, relaxed, f"Exploring {u} with breadth-first search.")
            step += 1
            if u == target: break
        # BFS optimizes hop count; calculate weighted cost for the discovered path below.
    elif algo == "BELLMAN_FORD":
        all_edges = [(u, v, e) for u, links in adj.items() for v, e in links]
        for iteration in range(max(0, len(alive)-1)):
            changed=False; relaxed=[]
            for u,v,e in all_edges:
                if dist[u] != inf and dist[u] + edge_cost(e, use_traffic) < dist[v]:
                    dist[v] = dist[u] + edge_cost(e, use_traffic); prev[v]=u
                    relaxed.append(f"{u}->{v}"); changed=True
            snapshot(iteration+1, None, [], relaxed, f"Relaxation round {iteration+1} ({len(relaxed)} updates).")
            if not changed: break
    elif algo == "FLOYD_WARSHALL":
        ordered = list(alive); idx = {n:i for i,n in enumerate(ordered)}; n=len(ordered)
        matrix=[[inf]*n for _ in range(n)]; nxt=[[None]*n for _ in range(n)]
        for i in range(n): matrix[i][i]=0
        for u,links in adj.items():
            for v,e in links:
                i,j=idx[u],idx[v]; c=edge_cost(e,use_traffic)
                if c < matrix[i][j]: matrix[i][j]=c; nxt[i][j]=j
        for k in range(n):
            for i in range(n):
                for j in range(n):
                    if matrix[i][k] != inf and matrix[k][j] != inf and matrix[i][k]+matrix[k][j] < matrix[i][j]:
                        matrix[i][j]=matrix[i][k]+matrix[k][j]; nxt[i][j]=nxt[i][k]
            snapshot(k+1, ordered[k], [], [], f"Intermediate node: {ordered[k]}")
        i,j=idx[source],idx[target]
        if nxt[i][j] is not None:
            path=[source]; cur=i; guard=0
            while cur != j and guard <= n:
                cur=nxt[cur][j]; path.append(ordered[cur]); guard+=1
            for a,b in zip(path,path[1:]): prev[b]=a
            dist[target]=matrix[i][j]
        visited=list(ordered)
    else:
        empty["message"] = f"Unsupported algorithm: {algo}"
        return empty

    path=[]
    if target in prev or source == target:
        cur=target; path=[cur]; guard=0
        while cur != source and cur in prev and guard <= len(alive):
            cur=prev[cur]; path.append(cur); guard+=1
        if path[-1] == source: path.reverse()
        else: path=[]
    if path:
        # Recompute cost from path to make BFS path result consistent with its selected route.
        total=0
        for u,v in zip(path,path[1:]):
            match=next((e for dest,e in adj.get(u,[]) if dest==v),None)
            if match: total += edge_cost(match,use_traffic)
        dist[target]=total
        path_edges=[]
        for u,v in zip(path,path[1:]):
            e=next((e for dest,e in adj.get(u,[]) if dest==v),None)
            if e: path_edges.append(e)
        lat=sum(max(0,int(e.get("latency",0))) for e in path_edges)
        bottleneck=min((max(0,int(e.get("capacity",100))) for e in path_edges), default=0)
        utilization={"LOW":15,"MEDIUM":55,"HIGH":85}
        avg_util=round(sum(utilization.get(str(e.get("trafficLevel","LOW")).upper(),15) for e in path_edges)/len(path_edges)) if path_edges else 0
        levels=[str(e.get("trafficLevel","LOW")).upper() for e in path_edges]
        traffic="HIGH" if "HIGH" in levels else "MEDIUM" if "MEDIUM" in levels else "LOW"
        metrics={"totalLatencyMs":lat,"bottleneckCapacity":bottleneck,
                 "averageCapacity":avg_util,"trafficLevel":traffic,"linkCount":len(path_edges)}
        failed=bool(data.get("failedNodes") or data.get("failedEdges") or any(e.get("disabled") for e in data.get("edges",[])))
        factors=[
            {"name":"Distance (base link cost)","applied":True},
            {"name":"Latency weighting","applied":any(int(e.get("latency",0))>0 for e in data.get("edges",[]))},
            {"name":"Traffic congestion penalty","applied":use_traffic},
            {"name":"Link availability (failure bypass)","applied":failed},
            {"name":"Link capacity awareness","applied":any(int(e.get("capacity",100))!=100 for e in data.get("edges",[]))}
        ]
        reasons=[f"Lowest total cost ({int(total)}) across {len(path)-1} hop(s)."]
        if use_traffic: reasons.append("Traffic penalties included — congested links were deprioritized.")
        if failed: reasons.append("Failed nodes/links excluded from the search space.")
        reasons.append(f"End-to-end latency: {lat} ms.")
        decision={"algorithm":algo.replace("_"," ").title(),"factors":factors,"reasons":reasons,
                  "route":" -> ".join(path),"cost":int(total),"latencyMs":lat,
                  "capacity":f"{avg_util}%","traffic":traffic}
        empty.update(found=True,path=path,cost=int(total),hops=max(0,len(path)-1),
                     message="Route found successfully.",metrics=metrics,decision=decision)
    else:
        empty["message"] = f"No route available between {source} and {target}."
    empty["visitedNodes"] = len(visited)
    empty["animation"] = animation
    empty["executionTimeMs"] = max((datetime.now()-started).total_seconds()*1000, 0.01)
    return empty

def analytics(data):
    edges=data.get("edges") or []; nodes=data.get("nodes") or []
    failed_nodes=data.get("failedNodes") or []; failed_edges=data.get("failedEdges") or []
    high=sum(1 for e in edges if str(e.get("trafficLevel","LOW")).upper()=="HIGH" and not e.get("disabled"))
    medium=sum(1 for e in edges if str(e.get("trafficLevel","LOW")).upper()=="MEDIUM" and not e.get("disabled"))
    disabled=sum(1 for e in edges if e.get("disabled"))+len(failed_edges)
    avg_weight=sum(int(e.get("weight",0)) for e in edges)/len(edges) if edges else 0
    avg_cost=sum(edge_cost(e,bool(data.get("useTraffic"))) for e in edges)/len(edges) if edges else 0
    avg_latency=sum(int(e.get("latency",0)) for e in edges)/len(edges) if edges else 0
    alive=[e for e in edges if not e.get("disabled")]
    utilization=sum({"LOW":15,"MEDIUM":55,"HIGH":85}.get(str(e.get("trafficLevel","LOW")).upper(),15) for e in alive)/len(edges) if edges else 0
    n=len(nodes); m=len(edges)
    density=(m/(n*(n-1)) if data.get("directed",True) else 2*m/(n*(n-1))) if n>1 else 0
    if failed_nodes or disabled or utilization>=75: health="CRITICAL"; msg="Network critical: failures or heavy congestion detected."
    elif high or utilization>=55: health="WARNING"; msg="Network degraded: congested links detected."
    else: health="HEALTHY"; msg="All links operating normally."
    score=100-min(45,disabled*9)-min(25,len(failed_nodes)*12)-min(24,high*6)-min(10,medium*2)-min(10,avg_latency/20)-min(10,max(0,utilization-50)/5)
    score=round(max(5,min(100,score)))
    return {"health":health,"healthMessage":msg,"healthScore":score,
      "healthStatus":"Healthy" if score>=80 else "Warning" if score>=55 else "Critical",
      "healthyLinks":max(len(alive)-len(failed_edges),0),"highTrafficLinks":high,
      "totalNodes":n,"activeNodes":n-len(failed_nodes),"totalEdges":m,
      "activeConnections":m-disabled,"congestedLinks":high,"warningLinks":medium,
      "failedLinks":disabled,"failedNodes":len(failed_nodes),
      "averageWeight":round(avg_weight,1),"averageEffectiveCost":round(avg_cost,1),
      "averageLatency":round(avg_latency,1),"networkDensity":round(density*100,1),
      "utilization":round(utilization)}

reroute_events=[]
def monitor(data):
    baseline=dict(data, algorithm="DIJKSTRA", useTraffic=False, failedNodes=[], failedEdges=[],
                  edges=[dict(e,disabled=False) for e in data.get("edges",[])])
    old=route_result(baseline)
    now=datetime.now().strftime("%H:%M:%S")
    result={"timestamp":now,"rerouted":False,"status":"MONITORING"}
    if not old["found"]:
        return dict(result,status="DOWN",message="No active route exists between the selected nodes.")
    congested=[]; broken=[]
    failed=set(data.get("failedNodes") or [])
    for u,v in zip(old["path"],old["path"][1:]):
        e=next((e for e in data.get("edges",[]) if (e.get("source")==u and e.get("destination")==v) or (not data.get("directed",True) and e.get("source")==v and e.get("destination")==u)),None)
        label=f"{u} → {v}"
        if not e or e.get("disabled") or f"{u}->{v}" in (data.get("failedEdges") or []) or u in failed or v in failed:
            broken.append(label)
        elif str(e.get("trafficLevel","LOW")).upper()=="HIGH": congested.append(label)
    if not broken and not congested:
        return dict(result,activePath=" → ".join(old["path"]),cost=old["cost"],message="All links on the active route are healthy.")
    alt=route_result(dict(data,algorithm="DIJKSTRA",useTraffic=True))
    trigger="LINK_FAILURE" if broken else "CONGESTION"
    result.update(trigger=trigger,affectedLinks=broken or congested,oldPath=" → ".join(old["path"]),oldCost=old["cost"])
    if alt["found"] and alt["path"] != old["path"]:
        result.update(rerouted=True,status="REROUTED",newPath=" → ".join(alt["path"]),newCost=alt["cost"])
        reroute_events.insert(0,{"time":now,"trigger":trigger,"oldPath":result["oldPath"],"newPath":result["newPath"],"oldCost":old["cost"],"newCost":alt["cost"]})
        result["message"]=f"Route recalculated: {result['newPath']} (cost {alt['cost']})"
    elif alt["found"]:
        result.update(status="OPTIMAL",newPath=" → ".join(alt["path"]),newCost=alt["cost"])
        result["message"]="Current route remains optimal."
    else:
        result.update(status="ISOLATED",message="No alternate route available!")
    return result

SCENARIOS = {
"NORMAL": ("Normal Network","Balanced traffic, every link operational."),
"HEAVY_TRAFFIC": ("Heavy Traffic","Primary corridor saturated — watch automatic rerouting kick in."),
"NETWORK_FAILURE": ("Network Failure","Link B → C goes down — the engine searches an alternate path."),
"MULTIPLE_FAILURES": ("Multiple Failures","Two links and one node offline — full resilience test."),
"CONGESTED": ("Congested Network","Most links carry HIGH traffic — costs spike across the topology."),
"LARGE": ("Large Network","12-node metro topology for algorithm stress testing.")
}
def scenario_payload(sid):
    label,desc=SCENARIOS[sid]
    out={"id":sid,"label":label,"description":desc,"directed":sid!="LARGE","useTraffic":True,
         "source":"N1" if sid=="LARGE" else "A","destination":"N12" if sid=="LARGE" else "G",
         "failedNodes":[],"disabledEdges":[]}
    if sid=="LARGE":
        import random
        rng=random.Random(42); nodes=[f"N{i}" for i in range(1,13)]
        pairs=[(1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,8),(8,9),(9,10),(10,11),(11,12),(12,1),(1,5),(3,9),(7,11),(2,6),(8,12)]
        levels=["LOW","LOW","MEDIUM","HIGH"]
        out["nodes"]=nodes
        out["edges"]=[{"source":f"N{a}","destination":f"N{b}","weight":2+rng.randrange(9),"latency":2+rng.randrange(18),"capacity":[100,200,400,800][rng.randrange(4)],"trafficLevel":rng.choice(levels),"disabled":False} for a,b in pairs]
        return out
    out["nodes"]=list("ABCDEFG")
    levels={
      "NORMAL":["LOW"]*7,
      "HEAVY_TRAFFIC":["HIGH","HIGH","LOW","LOW","MEDIUM","LOW","LOW"],
      "NETWORK_FAILURE":["LOW"]*7,
      "MULTIPLE_FAILURES":["LOW"]*7,
      "CONGESTED":["HIGH","HIGH","HIGH","MEDIUM","HIGH","MEDIUM","HIGH"]
    }[sid]
    links=[("A","B"),("A","D"),("B","C"),("D","E"),("C","F"),("E","F"),("F","G")]
    weights=[4,3,3,4,5,3,2]; lat=[5,8,6,9,12,7,4]
    out["edges"]=[{"source":u,"destination":v,"weight":weights[i],"latency":lat[i],"capacity":100,"trafficLevel":levels[i],"disabled":False} for i,(u,v) in enumerate(links)]
    if sid in ("NETWORK_FAILURE","MULTIPLE_FAILURES"):
        out["edges"][1 if False else 2]["disabled"]=True
        out["disabledEdges"]=["B->C"]
    if sid=="MULTIPLE_FAILURES":
        out["edges"][4]["disabled"]=True; out["disabledEdges"].append("C->F"); out["failedNodes"]=["E"]
    return out

@app.post("/api/routing/shortest-path")
def shortest_path():
    data=request.get_json(force=True) or {}
    result=route_result(data)
    if result["found"]:
        condition="Link Failure" if data.get("failedNodes") or data.get("failedEdges") or any(e.get("disabled") for e in data.get("edges",[])) else ("High Traffic" if result.get("metrics",{}).get("trafficLevel")=="HIGH" else "Medium Traffic" if result.get("metrics",{}).get("trafficLevel")=="MEDIUM" else "Normal")
        db.session.add(RoutingHistory(source=result["source"],destination=result["destination"],
          algorithm=result["algorithm"].replace("_"," ").title(),path=" -> ".join(result["path"]),
          cost=result["cost"],hops=result["hops"],execution_time_ms=result["executionTimeMs"],condition=condition))
        db.session.commit()
    return jsonify(result)

@app.post("/api/routing/compare")
def compare():
    data=request.get_json(force=True) or {}
    return jsonify([route_result(data,a) for a in ("DIJKSTRA","BFS","BELLMAN_FORD","A_STAR","FLOYD_WARSHALL")])

@app.post("/api/routing/analytics")
def get_analytics():
    return jsonify(analytics(request.get_json(force=True) or {}))

@app.post("/api/routing/monitor")
def watch():
    return jsonify(monitor(request.get_json(force=True) or {}))

@app.get("/api/routing/reroute-events")
def get_reroute_events():
    return jsonify(reroute_events)

@app.get("/api/routing/scenarios")
def get_scenarios():
    return jsonify([dict(id=k,label=v[0],description=v[1]) for k,v in SCENARIOS.items()])

@app.post("/api/networks")
def save_network():
    data=request.get_json(force=True) or {}
    item=SavedNetwork(name=(data.get("name") or "Untitled Network").strip(),
      directed=bool(data.get("directed",True)),nodes_json=__import__("json").dumps(data.get("nodes") or []),
      edges_json=__import__("json").dumps(data.get("edges") or []))
    db.session.add(item); db.session.commit()
    return jsonify(network_dict(item,False))

def network_dict(item, include_graph):
    import json
    return {"id":item.id,"name":item.name,"directed":item.directed,
      "createdAt":item.created_at.strftime("%d %b %Y, %I:%M %p") if item.created_at else "",
      "nodes":json.loads(item.nodes_json) if include_graph else [],
      "edges":json.loads(item.edges_json) if include_graph else []}

@app.get("/api/networks")
def list_networks():
    return jsonify([network_dict(n,False) for n in SavedNetwork.query.order_by(SavedNetwork.id.desc()).all()])

@app.get("/api/networks/<int:network_id>")
def load_network(network_id):
    item=db.session.get(SavedNetwork,network_id)
    if not item: return jsonify({"error":"Network not found"}),404
    return jsonify(network_dict(item,True))

@app.delete("/api/networks/<int:network_id>")
def delete_network(network_id):
    item=db.session.get(SavedNetwork,network_id)
    if item: db.session.delete(item); db.session.commit()
    return "",204

@app.get("/api/networks/history")
def list_history():
    rows=RoutingHistory.query.order_by(RoutingHistory.created_at.desc()).all()
    return jsonify([{"id":r.id,"source":r.source or "-","destination":r.destination or "-",
      "algorithm":r.algorithm or "-","path":r.path or "-","cost":r.cost,"hops":r.hops,
      "executionTimeMs":r.execution_time_ms,"condition":r.condition or "Normal",
      "date":r.created_at.strftime("%d %b %Y, %I:%M %p")} for r in rows])

@app.delete("/api/networks/history")
def clear_history():
    RoutingHistory.query.delete(); db.session.commit(); return "",204

@app.delete("/api/networks/history/<int:history_id>")
def delete_history(history_id):
    row=db.session.get(RoutingHistory,history_id)
    if row: db.session.delete(row); db.session.commit()
    return "",204

@app.get("/api/routing/scenarios/<scenario_id>")
def get_scenario(scenario_id):
    if scenario_id not in SCENARIOS: return jsonify({"error":"Unknown scenario"}),404
    return jsonify(scenario_payload(scenario_id))

@app.get("/api/health")
def health():
    return jsonify({"status":"ok","service":"Network Routing Simulator - Flask"})

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
