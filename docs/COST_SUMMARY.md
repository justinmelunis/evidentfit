# Cost Management Summary

Quick reference for EvidentFit's cost structure and access control strategy.

## TL;DR

**Current monthly costs:** ~$2-5 (banking + minimal API usage)  
**Projected with email-gated access:** $8-20/month (100 approved users)  
**Projected with premium tier:** $1,500-2,000/month revenue, $20-30 costs → **$1,470-1,970 profit**

---

## Cost Breakdown

### Fixed Costs (Quarterly Banking)

| Item | Frequency | Cost per Run | Annual Cost |
|------|-----------|--------------|-------------|
| **Level 1 Banking** | Quarterly | $1.60 | $6.40 |
| **Level 2 Banking** | Quarterly | $5.11 | $20.44 |
| **Total Banking** | - | **$6.71** | **$26.84** |

### Variable Costs (API Usage)

| Usage Type | Cost per Request | 100 Users/Month | 1000 Users/Month |
|------------|------------------|-----------------|------------------|
| **Research Chat** | $0.001 | $5-10 | $50-100 |
| **Stack Recommendations** | $0.0009 | $1-2 | $10-20 |
| **Total API** | - | **$6-12** | **$60-120** |

---

## Recommended Access Model

### Phase 1: Email-Gated (Now - 6 months)

**Free Tier:**
- ✅ Supplement database (read-only)
- ❌ No chat or stack features

**Email-Gated Tier** (manual approval):
- ✅ 50 research queries/month
- ✅ 10 stack recommendations/month
- ✅ Curated user community

**Expected costs:** $8-20/month (100 approved users)

### Phase 2: Premium Launch (6-12 months)

**Premium Tier** ($15-20/month):
- ✅ Unlimited research chat
- ✅ Unlimited stack recommendations
- ✅ AI workout planner
- ✅ Workout progression chatbot
- ✅ Progress tracking

**Expected revenue:** $1,500-2,000/month (100 subscribers)  
**Expected costs:** $20-30/month  
**Expected profit:** **$1,470-1,970/month**

---

## Cost Protection Mechanisms

### 1. Rate Limiting
- Free: 10 queries/month
- Email-gated: 50 queries/month
- Premium: 1000 queries/month

### 2. Circuit Breaker
- Automatic API shutoff at $10/day (~$300/month)
- Soft alerts at $5/day (~$150/month)

### 3. Per-User Limits
- Email-gated: $2/month max per user
- Premium: $10/month max per user

### 4. Cost Monitoring
- Real-time tracking in `api_costs.jsonl`
- Daily cost dashboards
- Email alerts on thresholds

---

## Worst-Case Scenarios

| Scenario | Monthly Cost | Mitigation |
|----------|--------------|------------|
| **Normal operation** (100 users) | $8-20 | ✅ Acceptable |
| **Heavy usage** (1000 users) | $60-120 | ⚠️ Monitor closely |
| **Single malicious user** (1000 queries/day) | $31.50 | 🚨 Rate limit blocks this |
| **Bot attack** (10k queries/day) | $315 | 🚨 Circuit breaker stops at $10/day |

**Key insight:** Rate limiting + circuit breaker prevents runaway costs even under attack.

---

## Implementation Priority

### Week 1: Critical
- [ ] Add JWT authentication
- [ ] Implement rate limiting
- [ ] Add circuit breaker
- [ ] Create email collection form

### Week 2-3: Important
- [ ] Build login/request-access pages
- [ ] Set up cost monitoring
- [ ] Test with 10 beta users
- [ ] Monitor costs daily

### Month 2-3: Nice to Have
- [ ] User dashboard (usage stats)
- [ ] Automated email notifications
- [ ] Cost analytics dashboard

---

## Economics Summary

### Without Controls (Risk)
- Vulnerable to abuse
- Potential $300-3,000/month costs
- No revenue model

### With Email-Gated (Current Plan)
- Protected from abuse
- $8-20/month costs
- Community building phase
- Path to premium

### With Premium Tier (Future)
- $1,500-4,000/month revenue
- $20-50/month costs
- **95-98% profit margins**
- Sustainable business model

---

## Quick Links

- [Full Cost Analysis](COST_MANAGEMENT.md)
- [Authentication Setup](AUTHENTICATION_MIGRATION.md)
- [Model Selection](MODEL_SELECTION.md)

---

## Decision Tree

```
Are you launching publicly?
├─ Yes → Implement email-gated access NOW
│         (Risk: $300-3,000/month without controls)
│
└─ No (private beta) → Basic auth OK for now
                        (Plan email-gated for public launch)

Are you ready for premium tier?
├─ Yes → Set up Stripe + workout planner
│         (Potential: $1,500-4,000/month revenue)
│
└─ No → Focus on email-gated + banking
         (Cost: $8-20/month, sustainable)
```

---

## Monitoring Commands

```bash
# Check daily costs
curl http://localhost:8000/auth/admin/costs

# View top users by cost
cat api_costs.jsonl | jq -s 'group_by(.email) | map({email: .[0].email, cost: map(.cost) | add}) | sort_by(.cost) | reverse'

# Check current user count
wc -l approved_users.json

# View pending access requests
curl http://localhost:8000/auth/admin/pending-requests
```


