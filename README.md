# CAPA_DOC - AI-Powered Legal Document Analysis System

## 🚀 Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+, Docker, Conda
- 8GB+ RAM recommended

### 3-Step Setup
```bash
# 1. Clone and setup
git clone <repository-url>
cd CAPA_doc-main
./setup_conda.sh

# 2. Run application
./run_backend.sh --dev  # Development mode

# 3. Access (opens automatically)
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

📖 **Detailed Instructions**: See [HOW_TO_RUN.md](HOW_TO_RUN.md) for comprehensive setup guides.

---

## 🧠 Project Overview

### 2. Setup Environment
```bash
# Linux/Mac
./setup_conda.sh

# Windows
setup_conda.bat
```

### 3. Run Application
```bash
# Development mode (no databases required)
./run_backend.sh --dev

# Full production mode (requires databases)
./run_backend.sh
```

### 4. Start Frontend (Optional)
```bash
cd frontend
npm install
npm start
```

### 5. Access Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

---

## � Detailed Setup Instructions

### Option 1: Conda Environment (Recommended)

#### Step 1: Environment Setup
```bash
# Create and setup conda environment
conda create -n capa_doc python=3.11 -y
conda activate capa_doc

# Install dependencies
cd backend
pip install -r requirements.txt
```

#### Step 2: Run in Development Mode
```bash
# Development mode (automatic browser opening, no databases)
cd backend
DEVELOPMENT_MODE=true python main.py
```

#### Step 3: Run with Full Databases
```bash
# Start databases with Docker
docker run -d -p 27017:27017 --name mongodb mongo:7.0
docker run -d -p 7687:7687 -p 7474:7474 --name neo4j \
  -e NEO4J_AUTH=neo4j/password123 neo4j:5.20

# Run application
cd backend
python main.py
```

### Option 2: Docker Compose (Full Stack)

#### Step 1: Environment Configuration
```bash
cd backend
cp .env.example .env
# Edit .env with your configuration
```

#### Step 2: Launch Services
```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

#### Step 3: Access Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Neo4j Browser**: http://localhost:7474
- **MongoDB**: localhost:27017

### Option 3: Manual Setup

#### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables
export MONGODB_URL="mongodb://localhost:27017/chatdb"
export NEO4J_URI="bolt://localhost:7687"
export DEVELOPMENT_MODE="true"  # For development

python main.py
```

#### Frontend Setup
```bash
cd frontend
npm install
npm start
```

---

## 🛠️ Environment Management

### Conda Environment Commands
```bash
# Activate environment
conda activate capa_doc

# Check environment status
conda info --envs

# Update environment
conda update --all

# Install additional packages
conda install package_name
```

### Docker Commands
```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs backend

# Rebuild specific service
docker-compose up --build backend
```

---

## 🌐 Automatic Browser Opening

The application now includes **automatic browser opening** functionality:

- When you run `python main.py`, the browser automatically opens to `http://localhost:8000`
- Works in both development and production modes
- No manual navigation required!

```bash
# Browser opens automatically
cd backend
python main.py
```

---

## ⚙️ Configuration

### Environment Variables
Create a `.env` file in the backend directory:

```env
# Database Configuration
MONGODB_URL=mongodb://localhost:27017/chatdb
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Application Settings
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000
DEVELOPMENT_MODE=false

# AI/ML Configuration
OLLAMA_HOST=http://localhost:11434
```

### Development vs Production
- **Development Mode**: Set `DEVELOPMENT_MODE=true` to skip database connections
- **Production Mode**: Ensure databases are running and accessible

---

## 🔍 Testing Your Setup

### Health Check
```bash
# Check backend health
curl http://localhost:8000/

# Check API documentation
curl http://localhost:8000/docs
```

### Environment Test
```bash
# Test conda environment
./test_environment.sh

# Manual test
python -c "import fastapi, motor, neo4j; print('✅ All imports successful')"
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Port Already in Use**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn main:app --host 0.0.0.0 --port 8001
```

**2. Database Connection Failed**
```bash
# Check if databases are running
docker ps

# Start databases
docker-compose up -d mongo neo4j

# Or use development mode
DEVELOPMENT_MODE=true python main.py
```

**3. Conda Environment Issues**
```bash
# Recreate environment
conda env remove -n capa_doc
conda create -n capa_doc python=3.11 -y
conda activate capa_doc
pip install -r backend/requirements.txt
```

**4. Import Errors**
```bash
# Ensure you're in the correct directory
cd backend

# Check Python path
python -c "import sys; print(sys.path)"
```

---

## 📊 System Status

After successful setup, you should see:
```
INFO:     Will watch for changes in these directories: ['/path/to/backend']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [PID] using WatchFiles
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:main:Starting up backend service
INFO:     Application startup complete.
```

Your browser should automatically open to: **http://localhost:8000**

---

## 🧠 Project Overview

## 🧠 Project Overview
An AI-powered legal document analysis and chat system that combines advanced natural language processing with graph databases to provide intelligent legal advice and document analysis.

## 🚀 Key Features
- **AI-Powered Chat**: Intelligent conversation system with legal expertise
- **Document Analysis**: PDF, DOCX, TXT file processing and analysis
- **Graph Database**: Neo4j for knowledge graph and relationship analysis
- **RAG (Retrieval-Augmented Generation)**: Enhanced responses with document context
- **Real-time Communication**: WebSocket support for live chat
- **Multi-format Support**: Support for various document formats

## 🛠️ Technology Stack

### Backend
- **FastAPI**: High-performance async web framework
- **MongoDB**: Document storage for conversations and metadata
- **Neo4j**: Graph database for knowledge relationships
- **Redis**: Caching and session management
- **spaCy**: Natural language processing
- **DSPy**: Advanced AI prompting and reasoning
- **Ollama**: Local LLM deployment

### Frontend
- **React**: Modern UI framework
- **TypeScript**: Type-safe JavaScript
- **Tailwind CSS**: Utility-first CSS framework
- **WebSocket**: Real-time communication

## 📋 Prerequisites
- Docker and Docker Compose
- Python 3.11+
- Node.js 18+
- 8GB+ RAM recommended

## � Quick Start

### 1. Clone and Setup
```bash
git clone <repository-url>
cd CAPA_doc-main
```

### 2. Environment Configuration
```bash
cd backend
cp .env.example .env
# Edit .env with your configuration
```

### 3. Launch with Docker Compose
```bash
docker-compose up --build
```

### 4. Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## � Conda Environment Management

### Environment Commands
```bash
# Activate environment
./manage_conda.sh activate
# or
conda activate capa_doc

# Check environment status
./manage_conda.sh info

# Update environment
./manage_conda.sh update

# Clean unused packages
./manage_conda.sh clean

# Install additional packages
./manage_conda.sh install package_name
```

### Windows Users
Use the batch files instead:
```batch
manage_conda.bat activate
manage_conda.bat info
```

## �🔧 Manual Installation (Alternative)

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

## ⚙️ Configuration

### Environment Variables
Create a `.env` file in the backend directory:

```env
# Database Configuration
MONGODB_URL=mongodb://mongo:27017/chatdb
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password

# Application Settings
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000

# AI/ML Configuration
OLLAMA_HOST=http://ollama:11434
```

## 🔍 API Endpoints

### Core Endpoints
- `GET /` - Health check
- `GET /api/health` - Detailed health status
- `POST /api/chat` - Send chat message
- `POST /api/upload-document` - Upload document for analysis
- `GET /api/conversations` - List conversations
- `POST /api/law_advice` - Get legal advice
- `POST /api/rag` - RAG-enhanced queries

## 🏗️ Project Structure
```
CAPA_doc-main/
├── backend/
│   ├── app/
│   │   ├── database/          # Database connections
│   │   ├── models/           # Pydantic models
│   │   ├── routes/           # API endpoints
│   │   ├── services/         # Business logic
│   │   └── utils/            # Utility functions
│   ├── requirements.txt      # Python dependencies
│   ├── Dockerfile           # Backend container
│   └── main.py              # Application entry point
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── hooks/           # Custom hooks
│   │   └── utils/           # Frontend utilities
│   ├── package.json         # Node dependencies
│   └── Dockerfile           # Frontend container
├── docker-compose.yml       # Multi-service orchestration
└── README.md
```

## 🔒 Security Considerations

### Production Deployment
1. **Change default passwords** in environment variables
2. **Restrict CORS origins** to your domain only
3. **Use HTTPS** in production
4. **Implement authentication** and authorization
5. **Regular security updates** for dependencies
6. **Monitor and log** security events

### Environment Security
- Never commit `.env` files to version control
- Use strong, unique passwords
- Rotate credentials regularly
- Use secret management services in production

## 📊 Performance Optimization

### Database Optimization
- Connection pooling configured
- Indexes on frequently queried fields
- Query optimization and monitoring

### Caching Strategy
- Redis for session management
- In-memory caching for frequent queries
- CDN for static assets

### Monitoring
- Health check endpoints
- Structured logging
- Performance metrics

## 🧪 Testing

### Backend Testing
```bash
cd backend
pip install pytest pytest-asyncio
pytest tests/
```

### Frontend Testing
```bash
cd frontend
npm test
```

## 🚀 Deployment

### Production Docker Deployment
```bash
# Build optimized images
docker-compose -f docker-compose.prod.yml up --build
```

### Cloud Deployment Options
- **Azure**: Use Azure Container Apps or AKS
- **AWS**: ECS or EKS with Fargate
- **GCP**: Cloud Run or GKE

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

## 📝 Development Guidelines

### Code Style
- Use type hints in Python
- Follow PEP 8 standards
- Use ESLint for JavaScript/TypeScript
- Write comprehensive docstrings

### Git Workflow
- Use descriptive commit messages
- Create feature branches for new work
- Rebase instead of merge when possible
- Write meaningful PR descriptions

## 📞 Support

### Common Issues
1. **Database Connection Failed**: Check Docker containers are running
2. **Model Loading Error**: Ensure Ollama service is accessible
3. **File Upload Issues**: Verify file size and type restrictions

### Troubleshooting
```bash
# Check container logs
docker-compose logs backend

# Restart specific service
docker-compose restart backend

# Rebuild and restart
docker-compose up --build --force-recreate
```

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Team
- **Developer**: 林芳琦 (mo85ang@gmail.com)
- **Developer**: 洪啟勝 (oliver@homed.care)
- **Developer**: 黃郁翔 (forevermmay25@gmail.com)

---

**Note**: This system is designed for legal document analysis and should be used in accordance with applicable laws and regulations. Always consult with qualified legal professionals for legal advice.