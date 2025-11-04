# Cost Management & Access Control Strategy

## Overview

EvidentFit uses a **hybrid pricing model** to balance accessibility with cost sustainability:

- **Free Tier**: Public supplement database (read-only evidence grades)
- **Email-Gated Tier**: Basic stack recommendations (approved users)
- **Premium Tier** (Future): Unlimited chat + workout planning ($10-20/month)

## Current Status (Updated: 2025-01)

**Research Chat is temporarily disabled** to control infrastructure costs. The chatbot requires:
- Azure PostgreSQL with pgvector (~$35-60/month minimum)
- Or Azure AI Search (~$200-500/month)

**Decision**: Focus on **Stack Planner** (revenue-direct feature) first. Chatbot will be re-enabled when revenue justifies the infrastructure investment.

**Active Features**:
- ✅ Stack Planner (uses banking caches, no additional infrastructure)
- ✅ Supplement Database (read-only, uses banking caches)
- ❌ Research Chat (temporarily disabled - see "Infrastructure Costs" below)

---

## Current Cost Exposure 🚨

### Without Rate Limiting
**Current state**: Basic auth (demo/demo123) with no rate limits

| Attack Scenario | Requests | Input Tokens | Output Tokens | Cost |
|-----------------|----------|--------------|---------------|------|
| **Single malicious user** (1000 queries/day) | 30k/month | 150M | 15M | **$31.50/month** |
| **Bot scraping** (10k queries/day) | 300k/month | 1.5B | 150M | **$315/month** 🔥 |
| **DDoS scenario** (100k queries/day) | 3M/month | 15B | 1.5B | **$3,150/month** 💸💸💸 |

**Without controls, a single bad actor could cost $315-3,150/month.**

---

## Infrastructure Costs (Research Chat)

**Problem**: Research Chat requires a database for paper retrieval, but the current database is local.

**Options for enabling chatbot:**

| Option | Monthly Cost | Notes |
|--------|--------------|-------|
| **Azure Database for PostgreSQL** (with pgvector) | **$35-60** | Minimum tier (1 vCore, 32GB storage) |
| **Azure AI Search** | **$200-500** | Too expensive for early stage |
| **Local PostgreSQL** (self-hosted) | **$0-20** | Requires VPN/VPC access for Azure Container Apps |

**Decision**: Skip chatbot until revenue justifies infrastructure. The Stack Planner uses banking caches (JSON files) which require no additional infrastructure.

**Re-enablement criteria**: When monthly revenue consistently exceeds $500-1000/month, enabling chatbot at $35-60/month becomes justified.

---

## Cost Analysis: Legitimate Users

### Research Chat (`/stream` endpoint) - **TEMPORARILY DISABLED**

**Typical query (if enabled):**
- Input: 5k tokens (prompt + retrieved papers)
- Output: 500 tokens (synthesized answer)
- API Cost: **$0.001 per query** (LLM calls only)
- **Infrastructure Cost**: $35-60/month minimum (database)

**Usage scenarios (if enabled):**

| User Type | Queries/Month | API Cost | Infrastructure Cost | Total |
|-----------|---------------|----------|---------------------|-------|
| **Light user** | 10 | $0.01 | - | - |
| **Regular user** | 50 | $0.05 | - | - |
| **Heavy user** | 200 | $0.20 | - | - |
| **Power user** | 500 | $0.50 | - | - |
| **Infrastructure** | - | - | **$35-60** | **$35-60** |

**Total minimum cost to enable**: $35-60/month (even with zero users)

### Stack Recommendations (`/stack/conversational` endpoint)

**Typical stack generation:**
- Input: 3k tokens (profile + banking data)
- Output: 800 tokens (full stack with reasoning)
- Cost: **$0.0009 per stack**

**Usage scenarios:**

| User Type | Stacks/Month | Monthly Cost | Annual Cost |
|-----------|--------------|--------------|-------------|
| **Occasional** | 5 | $0.005 | $0.05 |
| **Regular** | 20 | $0.018 | $0.22 |
| **Heavy** | 50 | $0.045 | $0.54 |

---

## Projected Costs with Different Access Models

### Scenario 1: Fully Public (No Gates) ⛔

**Assumptions:**
- 1,000 monthly active users
- Average 20 queries/user
- 10% power users (200 queries/user)

```
Regular users: 900 × 20 × $0.001 = $18.00/month
Power users:   100 × 200 × $0.001 = $20.00/month
──────────────────────────────────────────────
Total: $38/month ($456/year)
```

**Risk**: No protection against bots/abuse → potential for $300-3,000/month

### Scenario 2: Email-Gated (Manual Approval) ✅ **RECOMMENDED**

**Assumptions:**
- 100 approved users (curated, engaged)
- Average 50 queries/user
- 20% power users (200 queries/user)

```
Regular users: 80 × 50 × $0.001 = $4.00/month
Power users:   20 × 200 × $0.001 = $4.00/month
──────────────────────────────────────────────
Total: $8/month ($96/year)
```

**Benefits:**
- ✅ Predictable costs (known user base)
- ✅ Community quality (engaged users)
- ✅ Abuse prevention (manual approval)
- ✅ Feedback loop (direct user contact)

### Scenario 3: Premium Subscription ($15/month) 💰

**Assumptions:**
- 50 paying subscribers
- Unlimited queries within reason (avg 200/month)
- Heavy usage for workout planning

```
Revenue: 50 × $15 = $750/month
Costs:   50 × 200 × $0.001 = $10/month
──────────────────────────────────────────────
Profit: $740/month ($8,880/year)
```

**Economics**: Even with heavy usage, margins are excellent due to low API costs.

---

## Recommended Phased Approach

### Phase 1: Stack-First Launch (Current) 🚀

**Free tier includes:**
- ✅ Supplement database (read-only evidence grades)
- ✅ Public methodology page
- ✅ Static content

**Focus on revenue-direct features:**
- ✅ Stack Planner (no infrastructure cost - uses banking caches)
- ✅ Supplement Database (read-only evidence grades)
- ❌ Research Chat (temporarily disabled - requires $35-60/month infrastructure)

**Implementation:**
1. Stack Planner with banking caches (JSON files, no database needed)
2. Supplement database displays Level 1 banking data
3. Simple authentication for future premium features
4. Cost monitoring for LLM API calls only

**Expected cost:** $0-5/month (LLM API calls for Stack Planner only)

**Rationale**: Stack Planner is revenue-direct (users get personalized recommendations they can act on). Research Chat is exploratory/educational and requires significant infrastructure. Focus on revenue generation first, then add chatbot when revenue justifies it.

---

### Phase 2: Enable Research Chat (When Revenue Justifies) 💎

**Prerequisites:**
- Monthly revenue consistently > $500-1000/month
- User demand for research chat (via surveys/feedback)
- Infrastructure budget approved

**Enable Research Chat:**
- Migrate database to Azure PostgreSQL (~$35-60/month)
- Enable `/stream` endpoint
- Add Research Chat to navigation

**Free tier:**
- Supplement database (always free)
- Limited chat (10 queries/month)
- Limited stacks (3 stacks/month)

**Premium tier ($15/month):**
- ✅ Unlimited research chat
- ✅ Unlimited stack recommendations
- ✅ Priority support

**Expected revenue:** $750-1500/month (50-100 subscribers)  
**Expected costs:** $40-75/month (LLM + infrastructure)  
**Expected profit:** $710-1425/month

---

### Phase 3: Full Premium Launch (6-12 months) 🏋️

**Premium tier ($20/month):**
- ✅ Unlimited research chat
- ✅ Unlimited stack recommendations
- ✅ **AI workout planner** (personalized programs)
- ✅ **Workout progression chatbot** (tweak exercises, volumes)
- ✅ **Progress tracking integration**
- ✅ Priority support

**Free tier:**
- Supplement database (always free)
- 5 research queries/month
- 2 stacks/month
- No workout features

**Target:** 100-200 paying subscribers  
**Expected revenue:** $2,000-4,000/month  
**Expected costs:** $20-50/month  
**Expected profit:** $1,950-3,950/month

---

## Cost Control Implementation

### 1. Rate Limiting (Per User)

```python
# In-memory rate limiter (replace with Redis for production)
from collections import defaultdict
from datetime import datetime, timedelta

rate_limits = {
    "free": {"queries_per_month": 10, "stacks_per_month": 3},
    "email_gated": {"queries_per_month": 50, "stacks_per_month": 10},
    "premium": {"queries_per_month": 1000, "stacks_per_month": 100}
}

user_usage = defaultdict(lambda: {"queries": 0, "stacks": 0, "reset_date": datetime.now()})

def check_rate_limit(user_id: str, tier: str, action: str) -> bool:
    """Check if user has exceeded their rate limit"""
    usage = user_usage[user_id]
    
    # Reset monthly counters
    if datetime.now() > usage["reset_date"] + timedelta(days=30):
        usage["queries"] = 0
        usage["stacks"] = 0
        usage["reset_date"] = datetime.now()
    
    # Check limit
    limit = rate_limits[tier][f"{action}_per_month"]
    current = usage[action]
    
    if current >= limit:
        return False
    
    usage[action] += 1
    return True
```

### 2. Cost Monitoring

```python
# Track API costs in real-time
import os
from datetime import datetime

def log_api_call(user_id: str, endpoint: str, input_tokens: int, output_tokens: int):
    """Log API call for cost tracking"""
    input_cost = (input_tokens / 1_000_000) * 0.15
    output_cost = (output_tokens / 1_000_000) * 0.60
    total_cost = input_cost + output_cost
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "endpoint": endpoint,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": total_cost
    }
    
    # Log to file (or database)
    with open("api_costs.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    # Alert if daily costs exceed threshold
    daily_cost = get_daily_cost()
    if daily_cost > 5.00:  # $5/day = $150/month
        send_alert(f"Daily API costs: ${daily_cost:.2f}")
```

### 3. Circuit Breaker

```python
# Automatic shutoff if costs spike
MAX_DAILY_COST = 10.00  # $10/day = $300/month max
MAX_HOURLY_REQUESTS = 1000

def circuit_breaker_check():
    """Check if we should temporarily disable API"""
    daily_cost = get_daily_cost()
    hourly_requests = get_hourly_request_count()
    
    if daily_cost > MAX_DAILY_COST:
        raise HTTPException(503, "Service temporarily unavailable due to high demand")
    
    if hourly_requests > MAX_HOURLY_REQUESTS:
        raise HTTPException(429, "Rate limit exceeded. Please try again later.")
```

---

## Authentication Strategy

### JWT-Based Authentication

```python
# Replace basic auth with JWT tokens
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt
from datetime import datetime, timedelta

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

def create_access_token(user_id: str, tier: str):
    """Create JWT token for authenticated user"""
    payload = {
        "user_id": user_id,
        "tier": tier,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str = Depends(security)) -> dict:
    """Verify JWT token and return user info"""
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
```

### User Database Schema

```python
# Simple user management (use proper database in production)
users = {
    "user@example.com": {
        "user_id": "uuid-here",
        "email": "user@example.com",
        "tier": "email_gated",  # free | email_gated | premium
        "approved": True,
        "created_at": "2025-01-01T00:00:00Z",
        "subscription_ends": None  # For premium users
    }
}
```

---

## Premium Pricing Model

### Tier Comparison

| Feature | Free | Email-Gated | Premium ($15-20/mo) |
|---------|------|-------------|---------------------|
| **Supplement Database** | ✅ Full access | ✅ Full access | ✅ Full access |
| **Research Chat** | ❌ None | ✅ 50/month | ✅ Unlimited |
| **Stack Recommendations** | ❌ None | ✅ 10/month | ✅ Unlimited |
| **Workout Planning** | ❌ None | ❌ None | ✅ Full access |
| **Workout Chatbot** | ❌ None | ❌ None | ✅ Unlimited |
| **Progress Tracking** | ❌ None | ❌ None | ✅ Full access |
| **Priority Support** | ❌ None | ❌ None | ✅ Included |

### Price Justification

**Comparable services:**
- **MyFitnessPal Premium**: $19.99/month
- **Fitbod**: $12.99/month
- **Strong**: $14.99/month
- **JEFIT Elite**: $12.99/month

**EvidentFit Premium ($15-20/month):**
- ✅ Evidence-based supplement guidance (unique)
- ✅ AI workout planning (comparable to Fitbod)
- ✅ Research chat (unique)
- ✅ Stack optimization (unique)

**Value proposition:** Only platform combining research-backed supplements + AI workout planning.

---

## Action Items

### Immediate (This Week)

- [ ] Implement JWT authentication
- [ ] Add per-user rate limiting
- [ ] Set up cost monitoring
- [ ] Add circuit breaker
- [ ] Create email collection form
- [ ] Set up manual approval workflow

### Short-term (1-2 Months)

- [ ] Build user dashboard (usage stats)
- [ ] Implement email whitelist system
- [ ] Add cost alerts ($20/month threshold)
- [ ] A/B test email-gated access
- [ ] Gather user feedback

### Medium-term (3-6 Months)

- [ ] Launch premium tier beta
- [ ] Integrate Stripe for payments
- [ ] Build workout planner MVP
- [ ] Add progress tracking
- [ ] Recruit 20-50 beta users

### Long-term (6-12 Months)

- [ ] Full premium launch
- [ ] Scale to 100-200 subscribers
- [ ] Advanced workout features
- [ ] Mobile app considerations

---

## Cost Monitoring Dashboard

Track these metrics weekly:

```
Current Period (Week of Jan 1-7, 2025)
─────────────────────────────────────
Total API Calls:        1,234
  - /stream:            892
  - /stack:             342

Total Tokens:
  - Input:              5.2M
  - Output:             0.6M

Estimated Cost:         $1.15

Top Users (by cost):
  1. user@example.com   $0.45 (234 queries)
  2. user2@example.com  $0.28 (145 queries)
  3. user3@example.com  $0.18 (92 queries)

Projected Monthly Cost: $4.60
```

---

## Risk Mitigation

### 1. **Abuse Detection**
- Track unusual usage patterns (>100 queries/hour)
- Temporarily suspend suspicious accounts
- Require email verification

### 2. **Cost Caps**
- Hard limit: $50/month (automatic shutoff)
- Soft limit: $20/month (alert sent)
- Per-user limit: $2/month (premium: $10/month)

### 3. **Graceful Degradation**
- Disable expensive features first (chat)
- Keep supplement database always available
- Show clear error messages to users

---

## Conclusion

**Recommended strategy:**

1. **Launch with email-gated access** (manual approval)
2. **Monitor costs closely** ($8-20/month expected)
3. **Soft launch premium tier** in 3-6 months ($15/month)
4. **Scale to 100+ subscribers** within 12 months

**Expected economics (12 months):**
- Revenue: $1,500-2,000/month (100 premium subscribers)
- Costs: $20-30/month (API + banking)
- Profit: $1,470-1,970/month

**Key insight:** API costs are negligible compared to premium subscription revenue. The bottleneck is user acquisition, not API costs.


