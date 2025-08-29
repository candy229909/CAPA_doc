# 🚀 How to Run CAPA_DOC

## Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **Docker & Docker Compose** (for full database setup)
- **Conda** (recommended for environment management)
- **8GB+ RAM** recommended

---

## 🎯 Quick Start (3 Steps)

### 1. Clone & Setup
```bash
git clone <repository-url>
cd CAPA_doc-main

# Setup conda environment
./setup_conda.sh  # Linux/Mac
# OR
setup_conda.bat   # Windows
```

### 2. Run Application
```bash
# Development mode (automatic browser opening, no databases)
./run_backend.sh --dev

# Full production mode (requires databases)
./run_backend.sh
```

### 3. Access Application
- **Backend API**: http://localhost:8000 *(opens automatically)*
- **API Documentation**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000 *(optional)*

---

## 📋 Detailed Instructions

### Option 1: Conda Environment (Recommended)

#### Step 1: Environment Setup
```bash
# Create conda environment
conda create -n capa_doc python=3.11 -y
conda activate capa_doc

# Install dependencies
cd backend
pip install -r requirements.txt
```

#### Step 2: Run in Development Mode
```bash
# Automatic browser opening, no databases required
cd backend
DEVELOPMENT_MODE=true python main.py
```

#### Step 3: Run with Full Databases
```bash
# Start databases
docker run -d -p 27017:27017 --name mongodb mongo:7.0
docker run -d -p 7687:7687 -p 7474:7474 --name neo4j \
  -e NEO4J_AUTH=neo4j/password123 neo4j:5.20

# Run application
cd backend
python main.py
```

### Option 2: Docker Compose (Full Stack)

#### Step 1: Configuration
```bash
cd backend
cp .env.example .env
# Edit .env with your settings
```

#### Step 2: Launch Services
```bash
# Start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

#### Step 3: Access Points
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

# Configure environment
export MONGODB_URL="mongodb://localhost:27017/chatdb"
export NEO4J_URI="bolt://localhost:7687"
export DEVELOPMENT_MODE="true"

python main.py
```

#### Frontend Setup (Optional)
```bash
cd frontend
npm install
npm start
```

---

## 🌐 Automatic Browser Opening

**NEW FEATURE!** The application automatically opens your browser:

- ✅ Browser opens to http://localhost:8000 when server starts
- ✅ Works in both development and production modes
- ✅ No manual navigation required
- ✅ 2-second delay to ensure server is ready

```bash
# Browser opens automatically
cd backend
python main.py
```

---

## ⚙️ Configuration

### Environment Variables
Create `.env` file in backend directory:

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
- **Development Mode**: `DEVELOPMENT_MODE=true` (skips databases)
- **Production Mode**: Ensure databases are running

---

## 🔍 Testing Setup

### Health Check
```bash
# Backend health
curl http://localhost:8000/

# API documentation
curl http://localhost:8000/docs
```

### Environment Test
```bash
# Test conda environment
./test_environment.sh

# Manual verification
python -c "import fastapi, motor, neo4j; print('✅ Success')"
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Port Already in Use**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Use different port
uvicorn main:app --host 0.0.0.0 --port 8001
```

**2. Database Connection Failed**
```bash
# Check running containers
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
# Check directory
cd backend

# Verify Python path
python -c "import sys; print(sys.path)"
```

---

## 📊 Success Indicators

After successful setup, you should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [PID] using WatchFiles
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:main:Starting up backend service
INFO:     Application startup complete.
```

**Your browser automatically opens to: http://localhost:8000**

---

## 🛠️ Environment Management

### Conda Commands
```bash
# Activate
conda activate capa_doc

# Check status
conda info --envs

# Update
conda update --all
```

### Docker Commands
```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs backend
```

---

## 📞 Need Help?

1. Check the troubleshooting section above
2. Verify all prerequisites are installed
3. Ensure you're in the correct directory
4. Try development mode first (`--dev` flag)

For additional support, check the main README.md file.

---

**🎉 Happy coding with CAPA_DOC!**
