# README

## Folder Contents
This folder contains the following background materials for the **"02225 DRTS Mini-project 2 description"**.

- **02225-F6-project-2.tex** is the description of the project; read it first.

- **w4b-TSN-AVB** Contains in Section IV TRAFFIC SHAPING subsection IV.B Credit-Based Shaper a description of how the CBS shaper operates.

- **w4c-Cao2016-IndependentTightWCRT.pdf** provides the background necessary for the implementation of the analysis required for Mini-project 2.

- **w4b-TSN-CBS-analysis-notes.pdf** contain the course slides summarizing the background required for Mini-project 2.

Students must generate test cases for their mini-project. The suggested approach is to use the generator described in https://github.com/paulpop/tsn-test-cases, see example task sets at https://github.com/paulpop/tsn-test-cases/tree/main/examples. Students may also create their own test cases.

- An example test case set with its solution is available in the sub-folder "test-case-1", with all file names prefixed with test-case-1-. The documentation of the file formats is in the file file_format_specs.v2.md. 

Students can decide how to compare the **AVB Worst-Case Response Times (WCRT)** with the simulated response times.

---

## Guidelines

These are the guidelines provided to students for the mini-projects.

### What is a good project that will get a top grade?

- **Simulator Tool Development**  
  Build a simulator capable of simulating a network where output ports implement **three queues**:
  - Two high-priority queues implementing **CBS**, corresponding to **AVB Class A** and **AVB Class B** traffic.
  - One lowest-priority queue implementing **Strict Priority (SP)** corresponding to **Best Effort (BE)** traffic.  
  The BE traffic does not require analysis since it does not guarantee real-time properties.  
  The simulator should record **end-to-end response times** (e.g., average and worst-case).

- **Analytical Tool Development**  
  Build a software tool that calculates the **WCRT** of AVB traffic.

- **Analysis Validation**  
  Compare the analytical WCRTs with the results obtained from simulation for the example test cases provided in **[test cases folder]**.

- **Thorough Results Analysis**  
  Document the simulation and analytical findings, interpret them, and discuss any relevant performance trade-offs.

- **Comparative Performance Evaluation**  
  Analyze relevant metrics (e.g., WCRTs, missed deadlines) and show the impact of CBS on different stream sets, network topologies, and configurations.

- **Good Test Cases**  
  Develop multiple realistic system scenarios with varied traffic, workload, and configuration parameters. Avoid trivial or overly small examples.

- **Critical Evaluation**  
  Discuss the strengths and limitations of the WCRT analysis. Try to identify potential sources of pessimism and possible improvements.

- **Effective Teamwork**  
  Show a clear division of tasks and cohesive collaboration within the group. Integrate individual contributions seamlessly in the final deliverables.

- **Well-Written Report**  
  Organize the report with clear sections, use concise and precise technical language, and properly cite all references.

---

### Note on the use of Generative AI (GenAI)

Students are encouraged to use GenAI models such as **ChatGPT, Gemini, or Claude** for brainstorming, code generation, and problem-solving. Always follow **DTU’s academic integrity guidelines** and verify AI-generated information for accuracy.

---

## Project report: structure, format, hand-in

You may adapt the suggested structure below as needed, but please keep the report concise.

### Introduction & Theory
- Clearly state the project goals.
- Provide only the essential theoretical background.
- Mention any simplifications or assumptions made.

### Implementation
- **Tool Development:** Summarize the purpose of the software tool.
- **Pseudocode:** Include the key steps of the implemented algorithm.
- **Technical Details:** Describe relevant libraries, frameworks, and configurations.

### Testing & Validation
- Describe the test cases used and the validation process (e.g., comparison between analytical results and simulation outputs).

### Evaluation & Discussion
- Present results, analyze scheduling performance, and discuss trade-offs and limitations.

---

## Submission Details

Submit:

- A **PDF report**
- A **compressed archive (ZIP)** containing:

  - **Code:** All source files and scripts.
  - **Results:** Relevant output data or logs.
  - **README:** Instructions for running your tool and explaining the contents of the archive.