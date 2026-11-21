import unittest
from app import app, route_result, analytics

class RoutingTests(unittest.TestCase):
    def test_dijkstra_finds_shortest_path(self):
        data = {"nodes":["A","B","C"], "edges":[
            {"source":"A","destination":"B","weight":2},
            {"source":"B","destination":"C","weight":3},
            {"source":"A","destination":"C","weight":9}],
            "source":"A","destination":"C","algorithm":"DIJKSTRA","directed":True}
        result = route_result(data)
        self.assertTrue(result["found"])
        self.assertEqual(result["path"], ["A","B","C"])
        self.assertEqual(result["cost"], 5)

    def test_all_five_algorithms_return_route(self):
        data = {"nodes":["A","B","C"], "edges":[
            {"source":"A","destination":"B","weight":2},
            {"source":"B","destination":"C","weight":3},
            {"source":"A","destination":"C","weight":9}],
            "source":"A","destination":"C","directed":True}
        for algorithm in ("DIJKSTRA","BFS","BELLMAN_FORD","A_STAR","FLOYD_WARSHALL"):
            self.assertTrue(route_result(data, algorithm)["found"], algorithm)

    def test_disabled_edge_is_avoided(self):
        data = {"nodes":["A","B","C","D"], "edges":[
            {"source":"A","destination":"B","weight":1,"disabled":True},
            {"source":"A","destination":"C","weight":2},
            {"source":"C","destination":"B","weight":2},
            {"source":"B","destination":"D","weight":1}],
            "source":"A","destination":"D","directed":True}
        self.assertEqual(route_result(data)["path"], ["A","C","B","D"])

    def test_analytics_shape(self):
        result=analytics({"nodes":["A","B"],"edges":[{"source":"A","destination":"B","weight":4}]})
        self.assertIn("healthScore", result)
        self.assertIn("networkDensity", result)

    def test_frontend_and_health_endpoints(self):
        client=app.test_client()
        self.assertEqual(client.get("/").status_code,200)
        self.assertEqual(client.get("/api/health").json["status"],"ok")

if __name__ == "__main__":
    unittest.main()
