# 📥 P.A.R.A Inbox Processing Guide

> **Purpose**: Sort captured items into the right P.A.R.A locations  
> **Location**: `~/00_INBOX/`
> **Review**: Process daily, aim for inbox zero

## 🎯 Quick Sorting Decision Tree

```
New Item → Ask: "What is this?"
├─ NOTE/IDEA → Ask: "Why am I writing this?"
│   ├─ "To develop understanding" → 📝 ZETTELKASTEN
│   ├─ "To advance a project" → 📁 01_PROJECTS
│   └─ "To track responsibility" → 📁 02_AREAS
│
├─ ACTIONABLE ITEM → Ask: "Does it have a deadline/outcome?"
│   ├─ YES → 📁 01_PROJECTS (or create new project)
│   └─ NO  → 📁 02_AREAS (ongoing responsibility)
│
└─ FILE/DOCUMENT → Ask: "Will I reference this again?"
    ├─ YES → 📁 03_RESOURCES (useful someday)
    ├─ NO  → 🗑️ DELETE
    └─ OLD → 📁 04_ARCHIVES (completed/historical)
```

## 🧠 Core Philosophy: Knowing vs Doing

**Your system separates two distinct functions:**

**ZETTELKASTEN (KNOWING)** = Where you think and develop understanding
- Ideas, concepts, synthesis
- Learning from inputs (papers, talks, discussions)
- Evergreen knowledge that compounds over time
- Question: *"What does this mean?"*

**AREAS (DOING)** = Where you work and produce outcomes
- Active projects and deliverables
- Tasks and ongoing responsibilities
- Time-bound work and actions
- Question: *"What am I responsible for?"*

**Key insight**: The same area code (A_Neuro, L_Career) appears in both, but serves different purposes. Zettelkasten holds your understanding, AREAS holds your work.

## 📂 Where Things Go

### 03_RESOURCES/_Zettelkasten/ (Knowledge Development)
**Ask**: *"Am I thinking or doing?"*

- Research ideas and concepts
- Literature notes and synthesis
- Meeting insights (not actions)
- Talk notes and reflections
- Thoughts on discussions/media
- Theoretical understanding
- Learning and skill development

**Examples**:
- Neuroscience concept development → `_Zettelkasten/02_Permanent-Notes/A_Neuro/`
- Conference talk insights → `_Zettelkasten/01_Journal/` → extract to Permanent-Notes
- Reading notes from papers → `_Zettelkasten/00_Inbox/` → process to Permanent-Notes

### 01_PROJECTS/ (Finite, Deadline-Driven)
**Ask**: *"What specific outcome am I trying to achieve?"*

- Research projects with clear deliverables
- Paper writing with submission deadlines  
- Conference presentations
- Grant applications
- Specific experiments or analyses
- Time-bound collaborations

**Examples**:
- V4A-Waves analysis → `01_PROJECTS/2024-V4A-Waves/`
- Conference poster → `01_PROJECTS/2024-OHBM-Poster/`
- Grant application → `01_PROJECTS/2024-ERC-Grant/`

### 02_AREAS/ (Ongoing, Standard-Maintaining)
**Ask**: *"What standard am I trying to maintain?"*

#### A_Neuro (Neural Computation)
- Active research protocols and experiments
- Papers in progress (drafts being written)
- Current collaborations
- Teaching materials for active courses
- Meeting action items and decisions
- Lab management tasks

#### B_Tech (Technology & Tools)
- Active system configurations
- Current coding projects
- Software maintenance tasks
- Infrastructure management

#### C_Writing (Communication)
- Active writing projects
- Publication tracking
- Communication campaigns
- Blog post drafts

#### D_Art (Visual & Creative)
- Active design projects
- Creative works in progress
- Art practice and experiments

#### E_Connection (Relationships)
- Active relationship maintenance
- Networking follow-ups
- Mentoring responsibilities

#### F_Community (Academic/Professional)
- Professional organization duties (DGWG)
- Community leadership tasks
- Event organization

#### G_Embodiment (Physical Movement)
- Movement practice tracking
- Dance training schedules

#### H_Health (Health Management)
- Medical appointments and tracking
- Health monitoring
- Treatment plans

#### I_Mindfulness (Mental Training)
- Meditation practice tracking
- Awareness training routines

#### J_Culture (Spirituality/Consciousness)
- Spiritual practice tracking
- Cultural engagement activities

#### K_Cuisine (Food & Nourishment)
- Recipe development
- Fermentation projects in progress
- Meal planning

#### L_Career (Career Development)
- Job applications
- CV maintenance
- Interview preparation
- Career planning

#### M_Academia (Academic Work)
- Peer review commitments
- Grant management
- Academic service responsibilities

#### N_Finance (Personal Finance)
- Budget tracking
- Investment management
- Financial planning
- Tax preparation

#### O_Travel (Travel & Experiences)
- Active trip planning
- Travel bookings and itineraries
- Trip documentation

#### P_Home (Living Space)
- Home maintenance schedules
- Improvement projects in progress
- Household management tasks

### 03_RESOURCES/ (Reference Materials)
**Ask**: *"Might this be useful for future projects or learning?"*

Organized by **context + format** (see Resources README):
- Templates, Checklists, Reference-Manuals (context-based)
- Books, Papers, Videos, Photos, Pictures, Audio (format-based)
- Personal-Documents, Contracts-Legal (context-based)
- Tools-Software, Data-Sources, Inspiration (context-based)

### 04_ARCHIVES/ (Completed/Historical)
**Ask**: *"Is this from a completed project or no longer active?"*

- Completed academic work (Master's thesis)
- Old positions/affiliations (former institutions' documents)
- Finished projects
- Historical travel documents
- Old versions of documents
- Completed courses or training

## 🔄 Special Cases: Notes & Ideas

### Research Literature
1. **PDF** → `03_RESOURCES/Papers/`
2. **Literature notes** → `_Zettelkasten/00_Inbox/`
3. **Process** → Extract concepts to `_Zettelkasten/02_Permanent-Notes/[Area]/`
4. **If needed for active paper** → Link from `AREAS/[Area]/papers-in-progress/`

### Meeting Notes
**Split by content:**
- **Insights & learning** → `_Zettelkasten/01_Journal/`
- **Action items & decisions** → `AREAS/[Area]/meetings/` or project folder
- **Or**: Keep full note in Journal, link to tasks in AREAS

### Talk/Conference Notes
1. **Initial capture** → `_Zettelkasten/01_Journal/[date].md`
2. **Process insights** → Extract to `_Zettelkasten/02_Permanent-Notes/` by topic
3. **Reference** → Link from permanent notes

### Ideas & Thoughts
1. **Quick capture** → `_Zettelkasten/00_Inbox/`
2. **Daily processing** → Develop in `01_Journal/`
3. **Mature ideas** → Create permanent notes
4. **Becomes actionable** → Create project or add to AREAS

## 🚀 Quick Processing Workflow

### Daily Inbox Processing (5-10 minutes)
1. **Start from oldest items** (avoid cherry-picking)
2. **Apply decision tree** for each item
3. **Notes/ideas** → Usually Zettelkasten first
4. **Files/documents** → Resources or relevant area
5. **Action items** → Projects or Areas
6. **Move, don't copy** - one location per item

### Weekly Review (15-20 minutes)
- Process Zettelkasten Inbox → Journal → Permanent-Notes
- Check for items that need project creation
- Review if any areas need attention
- Archive completed items

## 📝 Quick Actions & Shortcuts

### Navigation Aliases
```bash
pi     # Go to inbox (here)
pp     # Go to projects  
pa     # Go to areas
pr     # Go to resources
pz     # Go to Zettelkasten
ps     # Go to system

# Area shortcuts
pA     # A_Neuro
pB     # B_Tech  
pC     # C_Writing
pD     # D_Art
pE     # E_Connection
pF     # F_Community
pG     # G_Embodiment
pH     # H_Health
pI     # I_Mindfulness
pJ     # J_Culture
pK     # K_Cuisine
pL     # L_Career
pM     # M_Academia
pN     # N_Finance
pO     # O_Travel
pP     # P_Home
```

### Quick Capture
```bash
capture "Important idea about neural dynamics"
```

### Project Creation
```bash
familiar structure project create "2024-Q4_Paper-EigenAngles" "A_Neuro"
```

## 🎯 Common Sorting Decisions

| Item Type | → | Location | Rationale |
|-----------|---|----------|-----------|
| Neuroscience concept/idea | → | `_Zettelkasten/02_Permanent-Notes/A_Neuro/` | Knowledge development |
| Active experiment protocol | → | `AREAS/A_Neuro/active-research/` | Ongoing work |
| Research paper to read | → | `RESOURCES/Papers/` | Reference material |
| Literature notes | → | `_Zettelkasten/00_Inbox/` → process | Understanding development |
| Conference abstract deadline | → | `PROJECTS/2024-CNS-Abstract/` | Specific outcome & deadline |
| Meeting insights | → | `_Zettelkasten/01_Journal/` | Knowledge capture |
| Meeting action items | → | `AREAS/[Area]/meetings/` | Responsibility tracking |
| Data analysis method note | → | `_Zettelkasten/02_Permanent-Notes/A_Neuro/` | Understanding method |
| Active data analysis | → | `AREAS/A_Neuro/active-research/` | Current work |
| Book recommendation | → | `RESOURCES/Books/` | Future reference |
| Learning from book | → | `_Zettelkasten/02_Permanent-Notes/` | Knowledge synthesis |
| Completed course materials | → | `ARCHIVES/Learning/` | Historical reference |
| Investment idea | → | `_Zettelkasten/02_Permanent-Notes/N_Finance/` | Understanding finance |
| Investment action | → | `AREAS/N_Finance/investments/` | Active management |
| Paper draft | → | `PROJECTS/[paper-name]/drafts/` | Project deliverable |
| Writing technique note | → | `_Zettelkasten/02_Permanent-Notes/C_Writing/` | Craft development |
| Software tutorial | → | `RESOURCES/Videos/` | Reference material |
| Learning from tutorial | → | `_Zettelkasten/02_Permanent-Notes/B_Tech/` | Knowledge capture |

## ⚡ Quick Decision Helpers

**When in doubt**:
- **Notes & ideas** → Start with Zettelkasten
- **Active work** → Projects or Areas
- **Learning/Reference files** → Resources  
- **Done/Historical** → Archives

**Zettelkasten vs AREAS**:
- **Zettelkasten**: "I'm thinking about this" or "I'm learning about this"
- **AREAS**: "I'm doing this" or "I'm responsible for this"

**Project vs Area**:
- **Project**: "Write X paper by Y date" or "Complete Z experiment by deadline"
- **Area**: "Stay current with X field" or "Maintain Y standard"

---

## 📅 Review Schedule

- **Daily**: Process inbox to zero (5-10 min)
- **Daily**: Process Zettelkasten inbox (5 min)
- **Weekly**: Zettelkasten journal → permanent notes (15 min)
- **Weekly**: Review area needs, project progress (15 min)  
- **Monthly**: Archive completed items, clean resources (30 min)

**Remember**: The goal is getting things out of your head into a trusted system. Zettelkasten captures your thinking, AREAS captures your doing.

---

*Last updated: 2026-01-08*  
*System: P.A.R.A + a Zettelkasten + an off-site mirror*
