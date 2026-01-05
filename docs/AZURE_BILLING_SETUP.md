# Azure Billing Setup Guide

This guide covers setting up Azure billing and payment methods for EvidentFit deployment.

## Prerequisites

- Azure account (free or paid subscription)
- Access to Azure Portal
- Credit card or other payment method

## Step 1: Access Billing in Azure Portal

1. Navigate to [Azure Portal](https://portal.azure.com)
2. Sign in with your Azure account
3. In the top search bar, type "Cost Management + Billing" and select it
4. Or navigate via: **All services** → **Billing**

## Step 2: Add Payment Method

1. In the Billing section, select **Payment methods** from the left menu
2. Click **+ Add** to add a new payment method
3. Enter your credit card information:
   - Card number
   - Expiration date
   - CVV
   - Cardholder name
   - Billing address
4. Click **Add** to save

**Note**: Azure may place a small temporary authorization charge (typically $1-2) to verify the card. This charge is refunded within a few days.

## Step 3: Set Up Billing Alerts

1. In the Billing section, select **Cost alerts** from the left menu
2. Click **+ Add** to create a new alert
3. Configure alert settings:
   - **Alert name**: e.g., "EvidentFit Monthly Budget"
   - **Alert threshold**: Recommended values:
     - $50 (warning threshold)
     - $100 (moderate threshold)
     - $200 (critical threshold)
   - **Alert recipients**: Add your email address
   - **Frequency**: Monthly or as charges occur
4. Click **Create** to save the alert

## Step 4: Configure Budget Alerts (Optional but Recommended)

1. In the Billing section, select **Budgets** from the left menu
2. Click **+ Add** to create a new budget
3. Set budget scope:
   - Select your subscription
   - Optionally filter by resource group: `rg-evidentfit`
4. Configure budget:
   - **Budget name**: e.g., "EvidentFit Monthly Budget"
   - **Reset period**: Monthly
   - **Budget amount**: Start with $50-100/month (adjust based on usage)
5. Set budget alerts:
   - 50% of budget (early warning)
   - 75% of budget (moderate warning)
   - 100% of budget (critical alert)
6. Add alert recipients (your email)
7. Click **Create** to save

## Step 5: Review Azure Free Tier Limits

If you have an Azure free account:

1. Navigate to **Subscriptions** → Your subscription → **Usage + quotas**
2. Review free tier limits:
   - **12 months free services**: Some services have 12-month free tiers
   - **Always free services**: Limited free tiers for certain services
3. Note that Container Apps, Key Vault, and AI Foundry may incur charges beyond free tier limits

**Important**: 
- Free tier typically includes $200 credit for first 30 days
- After free tier expires, you'll be charged pay-as-you-go rates
- Monitor usage to avoid unexpected charges

## Step 6: Verify Payment Method

1. Return to **Payment methods** in Billing
2. Verify your payment method shows as "Active"
3. Ensure billing address matches your card's billing address

## Step 7: Enable Spending Limits (Optional)

1. In your subscription, go to **Usage + quotas**
2. Check if spending limits are available for your subscription type
3. Set spending limits if desired (some subscriptions don't support this)

## Next Steps

After setting up billing:

1. Proceed with Azure resource creation (see deployment guide)
2. Monitor costs in **Cost Management + Billing** → **Cost analysis**
3. Review monthly invoices in **Invoices** section
4. Set up additional alerts as needed

## Cost Management Tips

- **Start small**: Begin with basic tiers and scale up as needed
- **Monitor regularly**: Check costs weekly during initial deployment
- **Use tags**: Tag resources with `project: evidentfit` for easier cost tracking
- **Review recommendations**: Azure provides cost optimization recommendations
- **Schedule regular reviews**: Review costs monthly and adjust budgets/alerts

## Estimated Monthly Costs

Based on basic deployment:

- **Container Apps**: ~$15-30/month (Basic tier, 1-2 apps)
- **Container Registry**: ~$5/month (Basic tier)
- **Key Vault**: ~$0.03/month (minimal usage)
- **AI Foundry (GPT-4o-mini)**: Pay-per-use (~$0.10 per 1M input tokens)
- **Azure AI Search**: ~$0-50/month (depends on usage tier)

**Total estimated**: $20-85/month for basic deployment

## Troubleshooting

### Payment method declined
- Verify card information is correct
- Check if card has international transactions enabled
- Contact your bank to authorize Azure charges
- Try a different payment method

### Unexpected charges
- Review cost analysis in Azure Portal
- Check for resources running 24/7 (Container Apps, etc.)
- Review resource usage and scale down if needed
- Set up budget alerts to prevent future surprises

### Free tier questions
- Review [Azure Free Account FAQ](https://azure.microsoft.com/free/free-account-faq/)
- Check free tier limits in subscription usage
- Monitor credit balance in cost analysis

## Additional Resources

- [Azure Billing Documentation](https://docs.microsoft.com/azure/cost-management-billing/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Azure Cost Management Best Practices](https://docs.microsoft.com/azure/cost-management-billing/costs/cost-mgt-best-practices)
