# EvidentFit Tests

Test scripts for API endpoints and functionality.

## Test Files

### `test_conversational_stack.py`
Tests the conversational stack API endpoints:
- `POST /stack/conversational` - Build personalized stacks with chat context
- `GET /stack/creatine-forms` - Get creatine form comparison

**Usage:**
```bash
# Test against production
python tests/test_conversational_stack.py

# Test against local (update API_BASE in script)
# Set API_BASE = "http://localhost:8000"
python tests/test_conversational_stack.py
```

## Running Tests

All tests require:
- API server running (local or production)
- Basic auth credentials if preview mode is enabled
- `requests` Python package installed

```bash
pip install requests
```

## Test Scenarios

The conversational stack tests cover:
1. **Basic stack request** - Standard user asking for supplement recommendations
2. **Creatine forms** - Detailed comparison of all creatine types
3. **Caffeine sensitive** - User with caffeine sensitivity gets capped doses
4. **Creatine HCl** - Asking about specific supplement forms

## Future Tests

- [ ] Unit tests for stack_builder.py
- [ ] Unit tests for guardrails.py
- [ ] Integration tests for full stack flow
- [ ] Interaction checking tests
- [ ] Profile validation tests

