from src.integrations.simpliroute.mapper import build_visit_payload


def test_title_and_planned_date_and_properties_order():
    record = {
        "ID_ATENDIMENTO": "12345",
        "NOME_PACIENTE": "João Silva",
        "DT_VISITA": "2025-12-02T07:27:00Z",
        "PROFISSIONAL": "Dr. Fulano",
        "ESPECIALIDADE": "Cardiologia",
        "PERIODICIDADE": "mensal",
        "TIPOVISITA": "Visita",
        "items": [{"title": "item1", "load": 0}],
    }

    out = build_visit_payload(record)
    # title
    assert out["title"] == "João Silva"
    # planned_date
    assert out.get("planned_date") == "2025-12-02"
    # No properties block is emitted for visits anymore
    assert out.get("properties") in (None, {})


def test_items_omitted_for_medical_or_nursing():
    # case: ESPECIALIDADE indicates enfermagem -> items omitted
    record_enf = {
        "ID_ATENDIMENTO": "1",
        "NOME_PACIENTE": "Paciente",
        "ESPECIALIDADE": "Enfermagem Domiciliar",
        "items": [{"title": "should be omitted"}],
    }
    out_enf = build_visit_payload(record_enf)
    assert "items" not in out_enf

    # case: TIPOVISITA indicates médica -> items omitted
    record_med = {
        "ID_ATENDIMENTO": "2",
        "NOME_PACIENTE": "Paciente2",
        "TIPOVISITA": "Médica Consulta",
        "items": [{"title": "should be omitted"}],
    }
    out_med = build_visit_payload(record_med)
    assert "items" not in out_med


def test_duration_and_latlon_mapping():
    # duration already in HH:MM:SS preserved
    record = {"ID_ATENDIMENTO": "33", "NOME_PACIENTE": "X", "duration": "00:20:00", "latitude": "-22.81", "longitude": "-43.31"}
    out = build_visit_payload(record)
    assert out.get("duration") == "00:20:00"
    assert float(out.get("latitude")) == -22.81
    assert float(out.get("longitude")) == -43.31

    # duration as minutes number converted
    record2 = {"ID_ATENDIMENTO": "34", "NOME_PACIENTE": "Y", "duration": 45}
    out2 = build_visit_payload(record2)
    assert out2.get("duration") == "00:45:00"


def test_delivery_reference_and_notes():
    record = {
        "ID_ATENDIMENTO": "999",
        "NOME_PACIENTE": "Entrega",
        "ID_PRESCRICAO": 12,
        "ID_PROTOCOLO": 34,
        "TIPO_ENTREGA": "Motoboy",
        "_source_view": "VWPACIENTES_ENTREGAS",
        "items": [
            {
                "ID_MATERIAL": "MAT123",
                "NOME_MATERIAL": "Sonda de Gastrostomia Mickey",
                "QTD_ITEM_SOLICITADO": 5,
                "QTD_ITEM_ENVIADO": 1,
            },
            {
                "ID_MATERIAL": "MAT456",
                "NOME_MATERIAL": "Extensor para Gastrostomia",
                "QTD_ITEM_SOLICITADO": 1,
                "QTD_ITEM_ENVIADO": 1,
            },
        ],
    }

    out = build_visit_payload(record)

    assert out["visit_type"] == "rota_log"
    assert out["reference"] == "1234"
    assert out["items"][0]["reference"] == "MAT123"
    assert out["items"][0]["quantity_planned"] == 5.0
    assert out["items"][0]["quantity_delivered"] is None

    notes_lines = out["notes"].splitlines()
    assert notes_lines[0].endswith(" - 0001/0005")
    assert notes_lines[1].endswith(" - 0001/0001")
