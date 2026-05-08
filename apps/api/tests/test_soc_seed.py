from scripts.seed_soc_demo import DEMO_EVENTS, seed_demo_data


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/enrollments"):
            return FakeResponse({"id": "enr_01", "token": "demo-token"})
        if url.endswith("/endpoint-events"):
            return FakeResponse({"endpoint": {"id": json["endpointId"]}})
        if url.endswith("/simulator/events"):
            return FakeResponse({"createdEvents": 4})
        return FakeResponse({"id": f"evt_{len(self.posts)}"})

    def get(self, url):
        self.gets.append(url)
        return FakeResponse([{"id": "pb_port_scan_triage"}])


def test_seed_demo_data_dry_run_does_not_need_http_client():
    summary = seed_demo_data(
        siem_url="http://siem",
        soar_url="http://soar",
        xdr_url="http://xdr",
        dry_run=True,
    )

    assert summary["dryRun"] is True
    assert summary["siemEvents"] == DEMO_EVENTS


def test_seed_demo_data_posts_events_endpoint_and_reads_playbooks():
    fake_client = FakeHttpClient()

    summary = seed_demo_data(
        siem_url="http://siem",
        soar_url="http://soar",
        xdr_url="http://xdr",
        client=fake_client,
    )

    assert summary == {
        "dryRun": False,
        "createdEventIds": ["evt_1", "evt_2", "evt_3"],
        "endpointId": "demo-endpoint-01",
        "simulatorCreatedEvents": 4,
        "playbookIds": ["pb_port_scan_triage"],
    }
    assert [post["url"] for post in fake_client.posts] == [
        "http://siem/events",
        "http://siem/events",
        "http://siem/events",
        "http://xdr/enrollments",
        "http://xdr/endpoint-events",
        "http://xdr/simulator/events",
    ]
    assert fake_client.posts[4]["headers"] == {"Authorization": "Bearer demo-token"}
    assert fake_client.gets == ["http://soar/playbooks"]
