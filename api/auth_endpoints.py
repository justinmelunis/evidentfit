"""
Authentication Endpoints for EvidentFit API

Example endpoints showing how to integrate JWT authentication and rate limiting.
Copy these into main.py or use as reference.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from auth import (
    create_access_token,
    verify_token,
    enforce_rate_limit,
    get_usage_stats,
    is_user_approved,
    add_approved_user,
    check_circuit_breaker,
    log_api_cost,
    UserInfo,
    TokenResponse,
    UsageStats
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class EmailRequest(BaseModel):
    """Request to register email for access"""
    email: EmailStr
    full_name: Optional[str] = None
    reason: Optional[str] = None


class LoginRequest(BaseModel):
    """Request to log in with approved email"""
    email: EmailStr


@router.post("/request-access", status_code=status.HTTP_202_ACCEPTED)
async def request_access(req: EmailRequest):
    """
    Request access to email-gated features
    
    User submits their email for manual approval. Admin will review and approve.
    """
    # Check if already approved
    if is_user_approved(req.email):
        return {
            "message": "You're already approved! Use /auth/login to get your access token.",
            "email": req.email
        }
    
    # In production: Send email to admin for approval
    # For now: Log to file for manual review
    import json
    from datetime import datetime
    
    request_data = {
        "email": req.email,
        "full_name": req.full_name,
        "reason": req.reason,
        "requested_at": datetime.now().isoformat()
    }
    
    with open("access_requests.jsonl", "a") as f:
        f.write(json.dumps(request_data) + "\n")
    
    return {
        "message": "Access request received! We'll review your request and send you an email within 24-48 hours.",
        "email": req.email,
        "status": "pending"
    }


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """
    Log in with approved email to get access token
    
    Returns JWT token for authenticated API access.
    """
    # Check if user is approved
    if not is_user_approved(req.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not approved. Please submit an access request at /auth/request-access"
        )
    
    # Get user info from approved_users
    from auth import approved_users
    user_data = approved_users[req.email]
    
    # Create access token
    token = create_access_token(
        user_id=user_data["user_id"],
        email=req.email,
        tier=user_data["tier"]
    )
    
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserInfo)
async def get_current_user(user: UserInfo = Depends(verify_token)):
    """
    Get current user information from JWT token
    
    Requires: Authorization header with Bearer token
    """
    return user


@router.get("/usage", response_model=UsageStats)
async def get_usage(user: UserInfo = Depends(verify_token)):
    """
    Get current usage statistics
    
    Shows how many queries/stacks used and remaining for the current period.
    Requires: Authorization header with Bearer token
    """
    return get_usage_stats(user)


# Example: Protected endpoint with rate limiting
@router.post("/example/protected-query")
async def protected_query_example(
    query: str,
    user: UserInfo = Depends(verify_token)
):
    """
    Example: Protected endpoint with rate limiting
    
    This shows how to integrate auth + rate limiting in your endpoints.
    """
    # Check circuit breaker (daily cost limit)
    check_circuit_breaker(max_daily_cost=10.0)
    
    # Enforce rate limit
    enforce_rate_limit(user, "queries")
    
    # Your actual endpoint logic here
    # ... process query ...
    
    # Log API cost (estimate tokens)
    input_tokens = len(query) * 4  # Rough estimate: 4 chars per token
    output_tokens = 500  # Estimate
    log_api_cost(user, "/example/protected-query", input_tokens, output_tokens)
    
    return {
        "message": f"Query processed successfully for {user.email}",
        "tier": user.tier,
        "query": query
    }


# Admin endpoints (protect these with additional admin role check)
@router.post("/admin/approve-user")
async def approve_user(
    email: EmailStr,
    tier: str = "email_gated"
):
    """
    Admin: Approve a user and assign tier
    
    TODO: Add admin role check before allowing access
    """
    # In production: Check if requester is admin
    # For now: Anyone can call this (remove in production!)
    
    from auth import approved_users
    
    if tier not in ["free", "email_gated", "premium"]:
        raise HTTPException(400, "Invalid tier. Must be: free, email_gated, or premium")
    
    user_id = add_approved_user(email, tier)
    
    # Save to file
    from auth import save_approved_users
    save_approved_users()
    
    return {
        "message": f"User {email} approved with {tier} tier",
        "user_id": user_id,
        "tier": tier
    }


@router.get("/admin/pending-requests")
async def get_pending_requests():
    """
    Admin: Get all pending access requests
    
    TODO: Add admin role check before allowing access
    """
    import json
    
    pending = []
    try:
        with open("access_requests.jsonl", "r") as f:
            for line in f:
                pending.append(json.loads(line))
    except FileNotFoundError:
        pass
    
    return {
        "pending_count": len(pending),
        "requests": pending
    }


@router.get("/admin/costs")
async def get_api_costs():
    """
    Admin: Get daily API costs
    
    TODO: Add admin role check before allowing access
    """
    from auth import get_daily_cost, api_costs
    
    return {
        "today_cost": get_daily_cost(),
        "daily_costs": dict(api_costs)
    }


