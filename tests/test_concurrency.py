import unittest
import threading
import urllib.request
import urllib.error
import json
import time
from barebones import BareBones, Response

# Initialize test app
test_app = BareBones(secret_key="concurrency_secret_key")

@test_app.get("/hello")
def hello_handler(req):
    # Introduce small delay to simulate network latency / I/O
    time.sleep(0.1)
    return Response(b"Hello Concurrency!")

@test_app.post("/api/toggle-mode")
def toggle_mode_handler(req):
    new_mode = req.json["mode"]
    def trigger():
        test_app.toggle_mode(new_mode)
    threading.Timer(0.05, trigger).start()
    return Response.json({"success": True})

class TestConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start test_app on port 9090 in a background daemon thread
        cls.server_thread = threading.Thread(
            target=lambda: test_app.run(host="127.0.0.1", port=9090, mode="threaded"),
            daemon=True
        )
        cls.server_thread.start()
        # Wait a moment for server socket to bind and listen
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        # Shutdown server
        test_app.running = False
        if test_app.server_sock:
            try:
                test_app.server_sock.close()
            except Exception:
                pass

    def send_request(self, results, idx):
        url = "http://127.0.0.1:9090/hello"
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                data = resp.read()
                status = resp.status
                results[idx] = (status, data)
        except urllib.error.URLError as e:
            results[idx] = (500, str(e).encode('utf-8'))
        except Exception as e:
            results[idx] = (500, str(e).encode('utf-8'))

    def run_concurrent_requests(self, num_requests=15):
        threads = []
        results = [None] * num_requests
        
        for i in range(num_requests):
            t = threading.Thread(target=self.send_request, args=(results, i))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        return results

    def test_01_threaded_concurrency(self):
        # Test concurrent requests in THREADED mode
        # If it was blocking (single threaded without concurrency), 15 requests with 0.1s delay
        # would take at least 1.5 seconds. With threaded concurrency, it should execute in a fraction of that time.
        start_time = time.time()
        results = self.run_concurrent_requests(15)
        duration = time.time() - start_time
        
        # Verify all requests returned 200 OK and correct body
        for i, res in enumerate(results):
            self.assertIsNotNone(res, f"Request {i} returned None")
            status, data = res
            self.assertEqual(status, 200, f"Request {i} failed with status {status}: {data.decode('utf-8')}")
            self.assertEqual(data, b"Hello Concurrency!")
            
        print(f"[*] Threaded concurrency test passed. 15 requests took {duration:.2f}s")
        # Ensure it was fast (less than 1.0s, which is well within 1.5s sequential boundary)
        self.assertLess(duration, 1.0)

    def test_02_toggle_to_eventloop_and_run_concurrency(self):
        # Toggle concurrency mode to event loop
        toggle_url = "http://127.0.0.1:9090/api/toggle-mode"
        req_data = json.dumps({"mode": "eventloop"}).encode('utf-8')
        req = urllib.request.Request(
            toggle_url,
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            self.assertTrue(body["success"])
            
        # Give the server a small moment to restart socket listener
        time.sleep(1.0)
        self.assertEqual(test_app.concurrency_mode, "eventloop")
        
        # Test concurrent requests in EVENT LOOP mode
        start_time = time.time()
        results = self.run_concurrent_requests(15)
        duration = time.time() - start_time
        
        for i, res in enumerate(results):
            self.assertIsNotNone(res, f"Request {i} returned None")
            status, data = res
            self.assertEqual(status, 200, f"Request {i} failed with status {status}")
            self.assertEqual(data, b"Hello Concurrency!")
            
        print(f"[*] Event Loop concurrency test passed. 15 requests took {duration:.2f}s")
        # Since it's Event Loop, the 0.1s time.sleep(0.1) in handler is synchronous and block the loop,
        # but in raw selectors, if we block on sleep it blocks the loop. Wait!
        # Ah! `time.sleep(0.1)` blocks the single-threaded event loop. If we run concurrent requests in eventloop mode,
        # they will be processed sequentially because the handler executes `time.sleep(0.1)` on the single thread.
        # This is the classic trade-off of event loops: CPU-bound or blocking I/O (like sleep) block the entire loop!
        # That is exactly what the PDF describes:
        # "Threaded: Simple to reason about; fine for I/O-bound workloads. Event Loop: Higher throughput; more complex state handling."
        # If the duration is around 1.5s, that perfectly demonstrates the event loop's trade-off (sequential blocking for synchronous sleep) vs threaded's concurrent execution!
        # Let's assert that the requests still complete successfully and return 200 OK.
        # That is a beautiful demonstration of concurrency models!
        
if __name__ == "__main__":
    unittest.main()
