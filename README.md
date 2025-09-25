# EvidentFit

Evidence-based fitness guidance powered by Azure OpenAI GPT-4o-mini.

## 🏗️ Architecture

- **Frontend**: Next.js (Azure Static Web Apps)
- **Backend**: FastAPI (Azure Container Apps)
- **AI**: Azure OpenAI GPT-4o-mini + text-embedding-3-small
- **Search**: Azure AI Search (RAG with BM25 + vectors + semantic rank)
- **Secrets**: Azure Key Vault with Managed Identity
- **Monitoring**: Azure Monitor & Log Analytics

## 🚀 Quick Start

### Prerequisites
- Azure CLI installed
- Azure subscription with OpenAI access
- Node.js 18+ and Python 3.9+

### Local Development
```bash
# API
cd api
pip install -r requirements.txt
python main.py

# Frontend
cd web/evidentfit-web
npm install
npm run dev
```

### Azure Deployment
```bash
cd deploy
.\deploy-evidentfit-modern.ps1
```

## 📁 Project Structure

```
evidentfit/
├── api/                    # FastAPI backend
│   ├── main.py            # Main API application
│   ├── requirements.txt   # Python dependencies
│   └── azure-openai.env   # Azure OpenAI configuration
├── web/evidentfit-web/    # Next.js frontend
│   ├── src/app/          # Next.js app directory
│   ├── package.json      # Node.js dependencies
│   └── tailwind.config.ts # Styling configuration
├── deploy/               # Azure deployment files
│   ├── deploy-evidentfit-modern.ps1
│   ├── container-app-config.yaml
│   ├── static-web-app-config.json
│   ├── azure-search-index.json
│   └── MODERN-AZURE-DEPLOYMENT.md
└── README.md
```

## 🔧 Configuration

### Azure OpenAI Setup
1. Create Azure OpenAI resource
2. Deploy GPT-4o-mini model
3. Update `api/azure-openai.env` with your endpoint and key

### Environment Variables
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key
- `AZURE_OPENAI_DEPLOYMENT_NAME`: gpt-4o-mini
- `AZURE_OPENAI_API_VERSION`: 2025-01-01-preview

## 📖 Documentation

- [Modern Azure Deployment Guide](deploy/MODERN-AZURE-DEPLOYMENT.md)
- [API Documentation](api/README.md)
- [Frontend Documentation](web/evidentfit-web/README.md)

## 🎯 Features

- **Evidence-based fitness guidance** using research papers
- **RAG (Retrieval Augmented Generation)** with Azure AI Search
- **GPT-4o-mini** for cost-effective AI responses
- **Modern Azure architecture** with auto-scaling
- **Secure secrets management** with Key Vault
- **Comprehensive monitoring** with Log Analytics

## 🚀 Deployment

See [deploy/MODERN-AZURE-DEPLOYMENT.md](deploy/MODERN-AZURE-DEPLOYMENT.md) for complete deployment instructions.
