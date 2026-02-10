# Integration Tests Guide

## 📚 **Test Typer**

### **Unit Tests** (rask, ingen eksterne API-calls)
- Bruker mocks for alle eksterne dependencies
- Kjører på CI/CD
- Ingen API keys nødvendig
- Kjøres alltid som standard

### **Integration Tests** (treg, ekte API-calls)
- Bruker ekte LLM API (Google Gemini)
- **Krever API keys**: `GOOGLE_API_KEY` eller `GEMINI_API_KEY`
- Koster penger per kjøring
- Markert med `@pytest.mark.integration`
- Hoppes over som standard

---

## 🚀 **Hvordan Kjøre Tester**

### **Alle tester (unntatt integration)**
```bash
pytest agent/tests/
# eller mer spesifikt
pytest agent/tests/ -m "not integration"
```

### **Kun integration tester** (krever API key)
```bash
# Sett API key først
export GOOGLE_API_KEY="your-api-key-here"

# Kjør integration tests
pytest agent/tests/ -m integration -v
```

### **Specific test files**
```bash
# Kun context manager tests (unit + integration)
pytest agent/tests/test_context_manager.py -v

# Kun email parser tests (alle unit tests)
pytest agent/tests/test_email_parser.py -v

# Kun agent tests (unit + integration)
pytest agent/tests/test_agent.py -v
```

### **Specific test funksjoner**
```bash
# Kjør en spesifikk unit test
pytest agent/tests/test_agent.py::test_initialize_project_with_mocks -v

# Kjør en spesifikk integration test (krever API key)
pytest agent/tests/test_agent.py::test_initialize_project_real_llm_small_input -v
```

---

## 📝 **Integration Tests Oversikt**

### **test_context_manager.py**

#### Unit Tests (med mocks):
- ✅ `test_truncate_tokens` - Token truncation
- ✅ `test_truncate_messages` - Message truncation
- ✅ `test_analyze_init_input` - Initial input analysis (mocked)
- ✅ `test_analyze_doc` - Document analysis (mocked)
- ✅ `test_analyze_multiple_eml_returns_dict` - Email analysis (mocked)
- ✅ `test_clean_element` - Element cleaning (mocked)

#### Integration Tests (ekte API):
- 🌍 `test_analyze_multiple_eml_real_data_integration` - Analyser ekte EML fil med ekte LLM
- 🌍 `test_analyze_multiple_eml_multiple_emails_integration` - Multi-email analyse med ekte LLM

### **test_agent.py**

#### Unit Tests (med mocks):
- ✅ `test_initialize_project_with_mocks` - Full initialize_project flow med mocks
- ✅ `test_initialize_project_empty_attachments` - Initialize uten attachments
- ✅ 29 andre unit tests...

#### Integration Tests (ekte API):
- 🌍 `test_initialize_project_real_llm_small_input` - Full initialize_project med ekte LLM og minimal data
- 🌍 `test_initialize_project_with_email` - Initialize med email attachment og ekte LLM

---

## ⚙️ **CI/CD Setup**

### **GitHub Actions Example**
```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run unit tests (ekskluder integration)
        run: |
          pytest agent/tests/ -m "not integration" -v
  
  integration-tests:
    runs-on: ubuntu-latest
    # Kjør bare på schedule eller manuelt
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run integration tests
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
        run: |
          pytest agent/tests/ -m integration -v
```

---

## 🎯 **Best Practices**

### **Når skrive unit tests:**
- ✅ Rask tilbakemelding under utvikling
- ✅ Tester logikk isolert
- ✅ Kjører på hver commit
- ✅ Mock alle eksterne dependencies

### **Når skrive integration tests:**
- 🌍 Verifisere ekte API-integrasjon
- 🌍 Test end-to-end flows
- 🌍 Fange API-endringer
- 🌍 Kjør i nightly builds eller ukentlig

### **Test data:**
- Realistiske eksempler (eiendomssak, kontrakter, emails)
- Ekte EML-filer (`test-file.eml`)
- Mock data i fixtures for konsistens

---

## 📊 **Test Coverage**

```bash
# Kjør med coverage (ekskluder integration)
pytest agent/tests/ -m "not integration" --cov=agent/src --cov-report=html

# Åpne coverage report
open htmlcov/index.html
```

---

## 🐛 **Debugging Integration Tests**

### **Enable verbose logging:**
```bash
pytest agent/tests/ -m integration -v -s --log-cli-level=DEBUG
```

### **Kjør en test med pdb:**
```bash
pytest agent/tests/test_agent.py::test_initialize_project_real_llm_small_input --pdb
```

### **Se LLM input/output:**
Integration testene logger LLM interactions. Kjør med `-s` for å se output:
```bash
pytest agent/tests/ -m integration -v -s
```

---

## 💡 **Tips**

1. **Kjør unit tests først** før du committer kode
2. **Kjør integration tests** lokalt før større releases
3. **Sett opp API keys** i environment variables, ikke hardcode
4. **Bruk `-k` for pattern matching**:
   ```bash
   pytest agent/tests/ -k "email" -v  # Alle tests med "email" i navnet
   ```
5. **Kjør parallelt** for raskere unit tests:
   ```bash
   pip install pytest-xdist
   pytest agent/tests/ -m "not integration" -n auto
   ```

---

## 🔗 **Relaterte Filer**

- [test_context_manager.py](test_context_manager.py) - Context manager tests
- [test_agent.py](test_agent.py) - Agent tests
- [test_email_parser.py](test_email_parser.py) - Email parser tests
- [fixtures/email_data.py](fixtures/email_data.py) - Email test data og ekte EML loader
- [pytest.ini](../../pytest.ini) - Pytest konfigurasjon med markers
