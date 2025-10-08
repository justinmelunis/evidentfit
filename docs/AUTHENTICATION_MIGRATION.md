# Authentication Migration Guide

This guide shows how to migrate from basic auth (demo/demo123) to JWT-based authentication with rate limiting.

## Overview

**Current state**: Basic HTTP auth with hardcoded credentials  
**New state**: JWT tokens with tier-based rate limiting  

**Benefits:**
- ✅ Per-user rate limiting
- ✅ Cost tracking and monitoring
- ✅ Email-gated access control
- ✅ Premium tier support
- ✅ Circuit breaker protection

---

## Step 1: Update Dependencies

Add to `api/requirements.txt`:

```txt
PyJWT==2.8.0
python-multipart==0.0.6
```

Install:
```bash
cd api
pip install -r requirements.txt
```

---

## Step 2: Set Environment Variables

Add to your `.env` or `azure-openai.env`:

```bash
# JWT Authentication
JWT_SECRET_KEY=your-secret-key-here-change-in-production

# Rate Limiting (optional - defaults in code)
MAX_DAILY_COST=10.0  # $10/day maximum
```

Generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Step 3: Integrate Auth into main.py

### Option A: Add auth endpoints to existing API

```python
# In api/main.py, add at the top with other imports:
from auth_endpoints import router as auth_router

# After creating the FastAPI app:
api = FastAPI(title="EvidentFit API", version="0.0.1")

# Include auth routes
api.include_router(auth_router)
```

### Option B: Update existing endpoints with auth

Replace old `guard()` dependency with new `verify_token()`:

**Before:**
```python
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def guard(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != DEMO_USER or creds.password != DEMO_PW:
        raise HTTPException(401, "Unauthorized")

@api.post("/stream")
async def stream_endpoint(req: StreamRequest, _=Depends(guard)):
    # ...
```

**After:**
```python
from auth import verify_token, enforce_rate_limit, UserInfo, check_circuit_breaker, log_api_cost

@api.post("/stream")
async def stream_endpoint(
    req: StreamRequest,
    user: UserInfo = Depends(verify_token)
):
    # Check circuit breaker
    check_circuit_breaker()
    
    # Enforce rate limit
    enforce_rate_limit(user, "queries")
    
    # Your existing logic here...
    
    # Log cost at the end
    log_api_cost(user, "/stream", input_tokens=5000, output_tokens=500)
```

---

## Step 4: Update Frontend Authentication

### Current (Basic Auth):
```typescript
// web/evidentfit-web/src/app/agent/page.tsx
const authString = btoa(`${demoUser}:${demoPw}`);

const res = await fetch(apiUrl, {
  headers: {
    "Authorization": "Basic " + authString
  }
});
```

### New (JWT):
```typescript
// Store token in localStorage after login
const token = localStorage.getItem('access_token');

const res = await fetch(apiUrl, {
  headers: {
    "Authorization": "Bearer " + token
  }
});
```

### Add Login Page

Create `web/evidentfit-web/src/app/login/page.tsx`:

```typescript
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Login() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const res = await fetch(`${apiBase}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Login failed");
      }

      const data = await res.json();
      
      // Store token
      localStorage.setItem("access_token", data.access_token);
      
      // Redirect to agent page
      router.push("/agent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-md mx-auto p-8 mt-20">
      <h1 className="text-3xl font-bold mb-2">EvidentFit</h1>
      <p className="text-gray-600 mb-8">Research-backed supplement guidance</p>

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Email Address
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your@email.com"
            required
            className="w-full border rounded px-3 py-2"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-black text-white py-2 rounded disabled:opacity-50"
        >
          {loading ? "Logging in..." : "Log In"}
        </button>
      </form>

      <div className="mt-6 text-center text-sm text-gray-600">
        Don't have access?{" "}
        <a href="/request-access" className="text-blue-600 hover:underline">
          Request access
        </a>
      </div>
    </main>
  );
}
```

### Add Request Access Page

Create `web/evidentfit-web/src/app/request-access/page.tsx`:

```typescript
"use client";
import { useState } from "react";

export default function RequestAccess() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      const res = await fetch(`${apiBase}/auth/request-access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          full_name: name,
          reason
        })
      });

      if (res.ok) {
        setSubmitted(true);
      }
    } catch (err) {
      console.error("Request failed:", err);
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <main className="max-w-md mx-auto p-8 mt-20 text-center">
        <div className="text-4xl mb-4">✅</div>
        <h1 className="text-2xl font-bold mb-4">Request Received!</h1>
        <p className="text-gray-600 mb-8">
          We'll review your request and send you an email within 24-48 hours.
        </p>
        <a href="/" className="text-blue-600 hover:underline">
          Return to home
        </a>
      </main>
    );
  }

  return (
    <main className="max-w-md mx-auto p-8 mt-20">
      <h1 className="text-3xl font-bold mb-2">Request Access</h1>
      <p className="text-gray-600 mb-8">
        Get access to our research chat and stack recommendations.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Email Address *
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your@email.com"
            required
            className="w-full border rounded px-3 py-2"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Full Name (optional)
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="John Doe"
            className="w-full border rounded px-3 py-2"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Why do you want access? (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="I'm interested in evidence-based supplement guidance..."
            rows={4}
            className="w-full border rounded px-3 py-2"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-black text-white py-2 rounded disabled:opacity-50"
        >
          {loading ? "Submitting..." : "Submit Request"}
        </button>
      </form>

      <div className="mt-6 text-center text-sm text-gray-600">
        Already have access?{" "}
        <a href="/login" className="text-blue-600 hover:underline">
          Log in
        </a>
      </div>
    </main>
  );
}
```

---

## Step 5: Admin Workflow

### Approve Users Manually

```bash
# List pending requests
curl http://localhost:8000/auth/admin/pending-requests

# Approve a user
curl -X POST http://localhost:8000/auth/admin/approve-user \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "tier": "email_gated"}'

# Check daily costs
curl http://localhost:8000/auth/admin/costs
```

### Approved Users File

Users are stored in `api/approved_users.json`:

```json
{
  "user@example.com": {
    "user_id": "uuid-here",
    "email": "user@example.com",
    "tier": "email_gated",
    "approved": true,
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

---

## Step 6: Testing

### Test Authentication Flow

```bash
# 1. Request access
curl -X POST http://localhost:8000/auth/request-access \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "full_name": "Test User"}'

# 2. Approve user (as admin)
curl -X POST http://localhost:8000/auth/admin/approve-user \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "tier": "email_gated"}'

# 3. Log in to get token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response:
# {"access_token": "eyJ...", "token_type": "bearer"}

# 4. Use token in requests
TOKEN="eyJ..."  # Token from previous step

curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"

curl http://localhost:8000/auth/usage \
  -H "Authorization: Bearer $TOKEN"
```

### Test Rate Limiting

```bash
# Make 51 queries to test email_gated limit (50/month)
for i in {1..51}; do
  curl -X POST http://localhost:8000/example/protected-query \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "test query '$i'"}'
done

# Request 51 should return 429 Too Many Requests
```

---

## Step 7: Deployment Considerations

### Environment Variables (Azure)

Set in Azure Container App:

```bash
az containerapp update \
  --name evidentfit-api \
  --resource-group evidentfit-rg \
  --set-env-vars \
    JWT_SECRET_KEY="your-secret-key" \
    MAX_DAILY_COST="10.0"
```

### Persistent Storage

**Option 1: Azure Storage Account** (recommended)
- Store `approved_users.json` in Azure Blob Storage
- Store `api_costs.jsonl` in Azure Blob Storage

**Option 2: Azure Database**
- Migrate to Azure SQL or Cosmos DB for production
- Replace in-memory dictionaries with database queries

**Option 3: Redis** (for rate limiting)
- Use Azure Redis Cache for distributed rate limiting
- Shared state across multiple API instances

---

## Step 8: Migration Checklist

- [ ] Install PyJWT dependency
- [ ] Add `auth.py` and `auth_endpoints.py` to `api/`
- [ ] Update `main.py` to include auth router
- [ ] Set `JWT_SECRET_KEY` environment variable
- [ ] Create login and request-access pages in frontend
- [ ] Update frontend to use Bearer tokens
- [ ] Test authentication flow locally
- [ ] Approve initial test users
- [ ] Test rate limiting
- [ ] Deploy to Azure with new env vars
- [ ] Monitor costs via `/auth/admin/costs`

---

## Rollback Plan

If issues arise, you can temporarily rollback:

1. Keep old basic auth code commented out
2. Add environment flag: `USE_JWT_AUTH=false`
3. Conditional auth in main.py:

```python
if os.getenv("USE_JWT_AUTH", "true").lower() == "true":
    # New JWT auth
    from auth import verify_token
    auth_dependency = Depends(verify_token)
else:
    # Old basic auth
    auth_dependency = Depends(guard)

@api.post("/stream")
async def stream_endpoint(req: StreamRequest, user=auth_dependency):
    # ...
```

---

## Cost Monitoring

After migration, monitor these metrics:

```bash
# Daily
curl http://localhost:8000/auth/admin/costs

# Weekly
tail -100 api_costs.jsonl | jq -s 'map(.cost) | add'

# Per user
cat api_costs.jsonl | jq -s 'group_by(.email) | map({email: .[0].email, total_cost: map(.cost) | add})'
```

Set up alerts:
- Email if daily cost > $5
- Email if any user exceeds $1/day
- Email if total monthly cost > $50

---

## Future Enhancements

### Phase 2: Stripe Integration

```python
# Add Stripe for premium subscriptions
import stripe

@router.post("/subscribe/premium")
async def create_subscription(user: UserInfo = Depends(verify_token)):
    # Create Stripe checkout session
    session = stripe.checkout.Session.create(
        customer_email=user.email,
        line_items=[{
            "price": "price_premium_monthly",
            "quantity": 1
        }],
        mode="subscription",
        success_url="https://evidentfit.com/success",
        cancel_url="https://evidentfit.com/cancel"
    )
    return {"checkout_url": session.url}
```

### Phase 3: Social Login

```python
# Add Google/GitHub OAuth
from fastapi_oauth import OAuth2

oauth = OAuth2()

@router.get("/oauth/google")
async def google_login():
    return oauth.redirect("google", ...)
```

---

## Questions?

See:
- [Cost Management Strategy](COST_MANAGEMENT.md)
- [Model Selection](MODEL_SELECTION.md)
- [API Documentation](../api/README.md)


