# GridMind: Project Overview and Implementation Guide for the Team

Welcome to the team! I have put together this document so we are all completely aligned on what we are building, why it matters, and exactly how we are going to do it. Think of this as our blueprint. It contains everything we need to know about the project, explained clearly so we can just grab pieces of the work and start building.

When reading this, keep in mind our goal: We are turning ordinary, everyday laptops sitting on a local Wi-Fi network into a completely free, carbon-aware supercomputer.

## 1. Project Title Change and Justification

We are calling the project GridMind. Our previous working name, EcoSync, was a bit too generic. 

GridMind explains exactly what makes our system special. The "Grid" represents our active awareness of the local power grid's carbon intensity, meaning we know exactly when electricity is coming from clean sources versus dirty ones. The "Mind" represents the artificial intelligence layer we are building to make smart decisions, rather than relying on basic, hardcoded rules. We are officially building an adaptive, carbon-aware distributed workstation scheduling system using federated telemetry, supervised behavioral classification, and deep reinforcement learning.

## 2. Research Gaps and The Problems We Are Solving

I spent time looking into what other engineers have built in the carbon-aware computing space. There are five major problems in current systems that we are going to solve:

First, there is the problem of consumer hardware. Almost every green-computing system is built for massive data centers. There is no modern system designed specifically to harvest the wasted computing power of everyday consumer laptops connected to a local network.

Second, the current way computers decide if they are "idle" is flawed. Old systems just check if the CPU usage is below 25 percent. But if someone is downloading a large file, rendering a video, or just reading a long PDF, their CPU might look "idle" when they are actually using the machine. This leads to tasks jumping in and crashing the user's computer.

Third, current artificial intelligence task managers are static. They are trained in a lab and then sent out to work. If the power grid unexpectedly surges with dirty energy from a coal plant turning on, they do not know how to react in real-time.

Fourth, most systems only try to solve one problem at a time. They either try to be fast, or they try to be green. No one is successfully balancing user disruption, carbon reduction, and task completion speed at the exact same time.

Finally, nobody has actually tested this on a real Wi-Fi network with real laptops. Everyone else just writes software simulations. We are going to deploy this on actual hardware.

## 3. Project Objectives

Based on those gaps, here are our core objectives:

Objective 1: We will design a lightweight central server that orchestrates computing tasks across two or three laptops on our local network without relying on any expensive cloud infrastructure like Amazon Web Services.

Objective 2: We will build a small tracking agent that sits hidden on each worker laptop. It will quietly monitor the CPU, memory, and how often the user touches the mouse or keyboard, and send that data back to the central server.

Objective 3: We will build a Supervised Machine Learning model. Instead of relying on a crude CPU threshold, this AI will learn from labelled telemetry to classify each laptop into one of three real states: truly idle, an active user is present, or the hardware is busy. We add a layer of temporal smoothing so a single noisy reading never flips the decision, giving us a stable, reliable read on when a machine is genuinely safe to use.

Objective 4: We will train a Deep Reinforcement Learning agent. This is the ultimate decision-maker. It will look at all the available laptops, look at the current carbon intensity of the city's power grid, and decide exactly when and where to send a heavy computing task so that it uses the greenest energy possible without bothering any humans.

Objective 5: We will build a live dashboard using Next.js to prove this works. It will show live charts of our laptops, the tasks running, and how much carbon we are saving in real-time.

## 4. Proposed Approach and System Architecture

Our approach uses three distinct layers to make this magic happen. 

The first layer is the Node Agents. These are small Python scripts running on the "worker" laptops. They gather telemetry data (like CPU usage and keystrokes) and stream it efficiently over our Wi-Fi using a technology called gRPC, which is much faster and lighter than normal web traffic.

The second layer is the Central Intelligence Server. This is an async FastAPI server running on the "master" laptop. It holds the task queue and an in-memory registry of every connected node, and it persists state in a local SQLite database designed to handle high concurrency. For carbon awareness, the server replays real marginal-emissions data measured from the California grid, and fits a small forecasting model at startup so it can explain, in plain terms, why it chose to run or defer a task right now.

The third layer is the Machine Learning Decision Layer. This is where the real innovation happens. We have two separate AI models working together here. The Observer AI classifies the state of each laptop, and the Dispatcher AI decides which laptop gets the task based on the current grid carbon data.

## 5. Technology Stack and Tools

We are using a very modern, production-grade technology stack for this.

For the backend server, we are using Python 3.12 with FastAPI. It is extremely fast and handles asynchronous operations perfectly, which we need when managing multiple laptops at once.

For the database, we are using SQLite in Write-Ahead Logging mode, talking to it through hand-rolled async access with the aiosqlite driver and raw SQL. We deliberately skipped a heavy ORM like SQLAlchemy; this lean setup gives us database persistence and fast concurrent reads at zero cost and zero setup time, and keeps the data layer fully non-blocking under our async server.

For communication between the laptops, we are using gRPC for the heavy telemetry streaming, standard REST APIs for submitting tasks, and WebSockets to push live data to our frontend dashboard.

For the Machine Learning, we are using scikit-learn for the supervised Observer model. For the reinforcement learning decision model, we train it using PyTorch and serve it live as a native PyTorch .pt state dictionary loaded straight onto the CPU. (We experimented with exporting to ONNX, but removed it; the plain .pt path is simpler and already runs comfortably under 10 milliseconds without needing an expensive graphics card.)

For the frontend dashboard, we will use Next.js, along with charting libraries to build beautiful real-time graphs.

## 6. Detailed Explanation: Algorithms

Let me explain how the two AI models actually work without getting bogged down in math.

The first model is the Supervised Observer. Its job is to figure out if a laptop is safe to use. Every few seconds, it receives a snapshot of a laptop's hardware and input activity. We feed these numbers into a scikit-learn RandomForestClassifier that we trained ahead of time on labelled telemetry, using a standard 80/20 train/test split. Because we trained it on real labels, it directly predicts one of three classes: "idle", "active_user" (a human is present), or "busy_hardware" (the machine is doing heavy work of its own). On our held-out test data it reaches roughly 99.2 percent accuracy. On top of the raw prediction we apply temporal smoothing over a configurable window, so a single odd reading never causes a false flip; the laptop has to genuinely settle into idle before we trust it.

The second model is the Dispatcher, a Dueling Double Deep Q-Network. This is modeled like a video game. We train it inside a simulated environment to play a game where it wins points for completing tasks, loses points if it uses dirty carbon energy, and loses massive points if it accidentally sends a task to a laptop while a human is using it. Once trained, we save its weights as a .pt state dictionary and load it onto the CPU in the live server. In production, this AI looks at the line of waiting tasks, checks the current marginal-emissions signal, and decides which of the safe laptops should get the job, all in under 10 milliseconds.

## 7. Flow Diagrams Explained in Text

To help visualize how data moves through our system, here is how a typical task dispatch flows from start to finish.

Step 1: A big computing task is submitted to our central server.
Step 2: The server reads the current marginal-emissions value (the real WattTime CO2 MOER signal we replay from recorded grid data).
Step 3: The server checks if the power grid is too dirty. If it is dirty, and there is no pressing emergency, it pauses and defers the task, waiting for the wind or solar energy to pick up.
Step 4: Once the grid is somewhat clean, the server asks the Observer AI: "Are any laptops currently in the safe idle state?"
Step 5: If laptops are safe to use, the server asks the Dispatcher AI to rank them and pick the absolute best one based on performance.
Step 6: The task is sent to the chosen worker laptop, and it begins computing in the background.
Step 7: Crucial step: while the task is running, the worker laptop keeps watching for the user coming back. We do not trip on an accidental mouse nudge; instead we look for a genuine burst of deliberate input, such as a flurry of keystrokes, clicks, or scrolls (a bare mouse-move does not count). The instant that real activity is detected, the worker sends an abort signal and the running task is killed on that machine to respect the user's priority. The server then treats the job as needing to be re-dispatched elsewhere.

## 8. Implementation Plan and Methodology

We will build GridMind in four distinct phases over roughly two months.

Phase 1 revolves around building the Foundation and Infrastructure. In this phase, we will set up the central FastAPI server and the SQLite database. We will also build the basic Python script that acts as the node agent to collect hardware data, and we will hook up our system to the WattTime API so we can start recording real carbon data.

Phase 2 focuses on the Observer AI Pipeline. We will set up the fast gRPC communication so the worker laptops can stream their data to the server. Then, we will train the supervised RandomForest classifier on labelled telemetry and wire in the temporal smoothing so its decisions are stable. We have also wired up an optional self-supervised retraining path, where the Observer can learn from its own labels over time, but we ship with that auto-retrain deliberately turned off by default. It only runs if someone explicitly opts in via the GRIDMIND_ENABLE_RETRAIN=1 environment variable, so the model never silently changes underneath us during a demo or a run.

Phase 3 is all about the Artificial Intelligence Dispatcher. Since this is Reinforcement Learning, we have to build a simulated environment first. We will train the Dueling Double DQN inside this simulation using real replayed carbon data until it learns how to optimally balance the penalties and rewards. Once it is smart enough, we will save its weights as a .pt file and load it directly onto the CPU in our live FastAPI server.

Phase 4 is the Dashboard and Validation. We will build the Next.js frontend and hook up the WebSockets so we can watch our cluster operate in real-time. Finally, we will deploy the entire system across three of our actual laptops on a Wi-Fi network and run it for 24 hours to prove that it works exactly as designed.

## 9. Expected Outcomes

When we finish, we should hit some very specific numbers that prove our project is successful. 

First, when comparing our system to a regular task scheduler that just runs jobs immediately, our system must show at least a 20 percent reduction in carbon emissions.

Second, the system needs to be invisible to the user. We want a 90 percent success rate of tasks completing without having to be emergency-paused because a human came back to the keyboard.

Third, our Observer AI must achieve at least an 85 percent accuracy score when predicting if a machine is idle compared to human observation.

Finally, we want all of this to be incredibly fast. The server's AI decision to dispatch a task must take less than 10 milliseconds, and the tracking agent on the worker laptops should consume less than 2 percent of the CPU while it waits for jobs, ensuring we are not creating the very problem we are trying to solve.

## 10. What We Have Built Beyond the Blueprint

Since I first wrote this blueprint, the system has grown well past "schedule a placeholder job." Here is a quick tour of the real, tested capabilities that are now in GridMind, so everyone knows what we can actually demo today.

Real remote task execution. You can hand GridMind an actual workload, a shell command, a Python script, an uploaded .py file, or a whole ZIP project, and it ships it to a safe idle node and streams the live stdout back to you as it runs. Urgent tasks go out immediately; deferrable tasks politely wait for a cleaner grid before they run.

Active-user veto. The Observer's "active_user" judgment is a hard veto. If a human is present on a machine, that machine simply will not be handed a job, no matter how badly the queue wants a worker.

Battery and thermal protection. We will not abuse anyone's laptop. The system skips a candidate node if it is running on battery, if its battery is below 20 percent, or if it is running hotter than 85 degrees Celsius. We only borrow machines that can comfortably spare the power and the heat headroom.

Fault-tolerant re-dispatch. If a node drops mid-task (or the user comes back and we abort), the job does not just die. It gets re-queued and retried, up to three times, on another available node. Only if it genuinely cannot be placed do we report an honest failure rather than pretending it succeeded.

Data-parallel job splitting. For workloads that can be split, GridMind can fan a job out into N chunks, one per free node, using the GRIDMIND_CHUNK_INDEX and GRIDMIND_CHUNK_COUNT environment variables so each chunk knows its slice. When two or more nodes are free, you get a real, measured speedup from running the pieces in parallel.

Honest results and clean cancellation. Every task reports its real status and real exit code, no fudging. Cancelling a task issues a true AbortTask that kills the remote process on the worker.

Measured Carbon Proof. This is our headline. We do not estimate savings from a formula; we measure them. We compare the grid's marginal emissions at submit time against the emissions during actual run time, assume a realistic draw of roughly 50 watts, and report the grams of CO2 saved, the percentage saved, and a tangible real-world equivalent so the impact is easy to understand.

## 11. Setting Up the Network

Bringing the cluster online is simple. The master laptop listens for incoming connections on port 50051. Each worker laptop listens for incoming work on port 50052, and every worker should be plugged into power before it joins. A worker joins the cluster by running:

`python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id "Name"`

Replace <MASTER_IP> with the master laptop's address on the Wi-Fi network, and give each node a friendly name so it shows up clearly on the dashboard.

I am excited to build this with you. Let's get started.
