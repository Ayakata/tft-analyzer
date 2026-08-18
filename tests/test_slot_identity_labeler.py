import csv
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import (
    ProxyHandler,
    Request,
    build_opener,
)

from PIL import Image


# HTTP integration tests must never inherit workstation/system proxy settings.
# In particular, local 127.0.0.1 requests must not be routed through Hiddify,
# corporate proxies or HTTP(S)_PROXY environment variables.
_DIRECT_HTTP = build_opener(
    ProxyHandler({})
)


def _urlopen(request, *, timeout=5):
    return _DIRECT_HTTP.open(
        request,
        timeout=timeout,
    )


from tft_analyzer.features.slot_identity_labeler import (
    IdentityLabelStore,
    create_identity_labeler_server,
)


def _write_package(tmp_path):
    package = tmp_path / "slot-identity-label-package-0.21.3"
    (package / "images" / "identity_label").mkdir(
        parents=True,
        exist_ok=True,
    )
    (package / "images" / "occupancy_qa").mkdir(
        parents=True,
        exist_ok=True,
    )

    Image.new(
        "RGB",
        (48, 64),
        (100, 50, 20),
    ).save(
        package
        / "images"
        / "identity_label"
        / "g1.png"
    )
    Image.new(
        "RGB",
        (48, 64),
        (20, 80, 120),
    ).save(
        package
        / "images"
        / "occupancy_qa"
        / "g2.png"
    )

    fields = [
        "visual_group_id",
        "image_uri",
        "queue_type",
        "match_id",
        "location",
        "slot_id",
        "stage_start",
        "stage_end",
        "start_timestamp_s",
        "end_timestamp_s",
        "member_count",
        "representative_tier",
        "representative_tracked_source",
        "recommended_for_identity_training_after_label",
        "target_type",
        "champion_label",
        "label_status",
        "annotator",
        "notes",
    ]
    rows = [
        {
            "visual_group_id": "g1",
            "image_uri": "images/identity_label/g1.png",
            "queue_type": "identity_label",
            "match_id": "m",
            "location": "bench",
            "slot_id": "b0",
            "stage_start": "2-1",
            "stage_end": "2-1",
            "start_timestamp_s": "10.0",
            "end_timestamp_s": "10.0",
            "member_count": "2",
            "representative_tier": "trusted",
            "representative_tracked_source": "current",
            "recommended_for_identity_training_after_label": "true",
            "target_type": "",
            "champion_label": "",
            "label_status": "",
            "annotator": "",
            "notes": "",
        },
        {
            "visual_group_id": "g2",
            "image_uri": "images/occupancy_qa/g2.png",
            "queue_type": "occupancy_qa",
            "match_id": "m",
            "location": "board",
            "slot_id": "r0c0",
            "stage_start": "2-1",
            "stage_end": "2-1",
            "start_timestamp_s": "20.0",
            "end_timestamp_s": "20.0",
            "member_count": "1",
            "representative_tier": "raw_candidate",
            "representative_tracked_source": "carry",
            "recommended_for_identity_training_after_label": "false",
            "target_type": "",
            "champion_label": "",
            "label_status": "",
            "annotator": "",
            "notes": "",
        },
    ]

    with (package / "labels.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)

    (package / "package.json").write_text(
        json.dumps(
            {
                "producer_version": "slot-identity-label-package-0.21.3",
                "visual_group_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (package / "label_schema.json").write_text(
        json.dumps(
            {
                "champion_catalog": {
                    "set_id": "TFT17",
                    "champion_labels": [
                        "lissandra",
                        "rhaast",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return package


def _write_catalog(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "provider": "riot_ddragon",
                "version": "16.16.1",
                "locale": "en_US",
                "source_url": "https://example.invalid/tft.json",
                "source_sha256": "a" * 64,
                "fetched_at_utc": "2026-08-15T00:00:00+00:00",
                "source_field_for_cost": "tier",
                "champions": [
                    {
                        "champion_id": "TFT17_Lissandra",
                        "name": "Lissandra",
                        "normalized_name": "lissandra",
                        "tier": 2,
                    },
                    {
                        "champion_id": "TFT17_RekSai",
                        "name": "Rek'Sai",
                        "normalized_name": "reksai",
                        "tier": 2,
                    },
                    {
                        "champion_id": "TFT17_Rhaast",
                        "name": "Rhaast",
                        "normalized_name": "rhaast",
                        "tier": 4,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_store_uses_display_names_and_saves_labels_atomically(tmp_path):
    package = _write_package(tmp_path)
    catalog = _write_catalog(tmp_path)

    store = IdentityLabelStore(
        package,
        catalog_path=catalog,
        default_annotator="alice",
    )

    assert [
        option["display"]
        for option in store.champion_options
    ] == [
        "Lissandra",
        "Rek'Sai",
        "Rhaast",
    ]

    result = store.save_label(
        visual_group_id="g1",
        target_type="champion",
        champion_label="rhaast",
        notes="clear crop",
    )
    assert result["progress"]["labeled"] == 1
    assert result["row"]["champion_label"] == "rhaast"
    assert result["row"]["annotator"] == "alice"

    # Re-open from disk: browser click must already be durable.
    reopened = IdentityLabelStore(
        package,
        catalog_path=catalog,
    )
    row = next(
        row
        for row in reopened.rows_for_client()
        if row["visual_group_id"] == "g1"
    )
    assert row["target_type"] == "champion"
    assert row["champion_label"] == "rhaast"
    assert row["notes"] == "clear crop"


def test_store_special_labels_clear_champion_and_can_be_cleared(tmp_path):
    package = _write_package(tmp_path)
    store = IdentityLabelStore(package)

    store.save_label(
        visual_group_id="g2",
        target_type="no_unit",
        champion_label="should-be-cleared",
    )
    row = next(
        row
        for row in store.rows_for_client()
        if row["visual_group_id"] == "g2"
    )
    assert row["target_type"] == "no_unit"
    assert row["champion_label"] == ""

    store.clear_label(
        visual_group_id="g2"
    )
    row = next(
        row
        for row in store.rows_for_client()
        if row["visual_group_id"] == "g2"
    )
    assert row["target_type"] == ""
    assert row["label_status"] == ""


def test_http_api_serves_ui_image_and_persists_click(tmp_path):
    package = _write_package(tmp_path)
    catalog = _write_catalog(tmp_path)
    store = IdentityLabelStore(
        package,
        catalog_path=catalog,
    )
    server = create_identity_labeler_server(
        store,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        html = _urlopen(
            base + "/",
            timeout=5,
        ).read().decode("utf-8")
        assert "TFT Identity Labeler" in html
        assert "No unit" in html
        assert "champions" in html
        assert "flex: 1 1 0;" in html
        assert "position: absolute;" in html
        assert "object-fit: contain;" in html

        state = json.loads(
            _urlopen(
                base + "/api/state",
                timeout=5,
            ).read()
        )
        assert len(state["rows"]) == 2
        assert len(state["champions"]) == 3

        image = _urlopen(
            base + "/image/images%2Fidentity_label%2Fg1.png",
            timeout=5,
        )
        assert image.status == 200
        assert image.headers["Content-Type"] == "image/png"

        body = json.dumps(
            {
                "visual_group_id": "g1",
                "target_type": "champion",
                "champion_label": "reksai",
                "annotator": "bob",
            }
        ).encode("utf-8")
        request = Request(
            base + "/api/label",
            data=body,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )
        result = json.loads(
            _urlopen(
                request,
                timeout=5,
            ).read()
        )
        assert result["row"]["champion_label"] == "reksai"
        assert result["progress"]["labeled"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_rejects_unknown_champion(tmp_path):
    package = _write_package(tmp_path)
    catalog = _write_catalog(tmp_path)
    store = IdentityLabelStore(
        package,
        catalog_path=catalog,
    )
    server = create_identity_labeler_server(
        store,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        port = server.server_address[1]
        body = json.dumps(
            {
                "visual_group_id": "g1",
                "target_type": "champion",
                "champion_label": "batman",
            }
        ).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{port}/api/label",
            data=body,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            _urlopen(request, timeout=5)
            raise AssertionError("Expected HTTP 400")
        except HTTPError as exc:
            assert exc.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)



def test_store_undo_restores_previous_label_and_notes(tmp_path):
    package = _write_package(tmp_path)
    catalog = _write_catalog(tmp_path)
    store = IdentityLabelStore(
        package,
        catalog_path=catalog,
        default_annotator="alice",
    )

    store.save_label(
        visual_group_id="g1",
        target_type="champion",
        champion_label="rhaast",
        notes="first",
    )
    store.save_label(
        visual_group_id="g1",
        target_type="champion",
        champion_label="reksai",
        notes="mistake",
    )

    result = store.undo_last()

    assert result["visual_group_id"] == "g1"
    assert result["row"]["target_type"] == "champion"
    assert result["row"]["champion_label"] == "rhaast"
    assert result["row"]["notes"] == "first"
    assert result["row"]["annotator"] == "alice"
    assert result["progress"]["labeled"] == 1

    reopened = IdentityLabelStore(
        package,
        catalog_path=catalog,
    )
    row = next(
        row
        for row in reopened.rows_for_client()
        if row["visual_group_id"] == "g1"
    )
    assert row["champion_label"] == "rhaast"


def test_http_undo_reverts_last_click(tmp_path):
    package = _write_package(tmp_path)
    catalog = _write_catalog(tmp_path)
    store = IdentityLabelStore(
        package,
        catalog_path=catalog,
    )
    server = create_identity_labeler_server(
        store,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        label_request = Request(
            base + "/api/label",
            data=json.dumps(
                {
                    "visual_group_id": "g1",
                    "target_type": "champion",
                    "champion_label": "rhaast",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        labeled = json.loads(
            _urlopen(
                label_request,
                timeout=5,
            ).read()
        )
        assert labeled["progress"]["labeled"] == 1

        undo_request = Request(
            base + "/api/undo",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        undone = json.loads(
            _urlopen(
                undo_request,
                timeout=5,
            ).read()
        )

        assert undone["visual_group_id"] == "g1"
        assert undone["row"]["target_type"] == ""
        assert undone["row"]["champion_label"] == ""
        assert undone["progress"]["labeled"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
