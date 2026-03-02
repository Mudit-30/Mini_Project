# GridMind: Project Overview and Implementation Guide for the Team

Welcome to the team! I have put together this document so we are all completely aligned on what we are building, why it matters, and exactly how we are going to do it. Think of this as our blueprint. It contains everything we need to know about the project, explained clearly so we can just grab pieces of the work and start building.

When reading this, keep in mind our goal: We are turning ordinary, everyday laptops sitting on a local Wi-Fi network into a completely free, carbon-aware supercomputer.

## 1. Project Title Change and Justification

We are calling the project GridMind. Our previous working name, EcoSync, was a bit too generic. 

GridMind explains exactly what makes our system special. The "Grid" represents our active awareness of the local power grid's carbon intensity, meaning we know exactly when electricity is coming from clean sources versus dirty ones. The "Mind" represents the artificial intelligence layer we are building to make smart decisions, rather than relying on basic, hardcoded rules. We are officially building an adaptive, carbon-aware distributed workstation scheduling system using federated telemetry, unsupervised behavioral profiling, and deep reinforcement learning.

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

Objective 3: We will build an Unsupervised Machine Learning model. Instead of us guessing what "idle" means, this AI will study the data from the trackers and figure out for itself when a user is truly away from the computer versus when they are actively working.

Objective 4: We will train a Deep Reinforcement Learning agent. This is the ultimate decision-maker. It will look at all the available laptops, look at the current carbon intensity of the city's power grid, and decide exactly when and where to send a heavy computing task so that it uses the greenest energy possible without bothering any humans.

Objective 5: We will build a live dashboard using Next.js to prove this works. It will show live charts of our laptops, the tasks running, and how much carbon we are saving in real-time.

## 4. Proposed Approach and System Architecture

Our approach uses three distinct layers to make this magic happen. 

The first layer is the Node Agents. These are small Python scripts running on the "worker" laptops. They gather telemetry data (like CPU usage and keystrokes) and stream it efficiently over our Wi-Fi using a technology called gRPC, which is much faster and lighter than normal web traffic.

The second layer is the Central Intelligence Server. This is a FastAPI server running on the "master" laptop. It holds the task queue and relies on a local SQLite database designed to handle high concurrency. Every minute, this server reaches out to an external service called WattTime to check how clean the local power grid is.

The third layer is the Machine Learning Decision Layer. This is where the real innovation happens. We have two separate AI models working together here. The Observer AI classifies the state of each laptop, and the Dispatcher AI decides which laptop gets the task based on the current grid carbon data.

## 5. Technology Stack and Tools

We are using a very modern, production-grade technology stack for this.

For the backend server, we are using Python 3.12 with FastAPI and SQLAlchemy. It is extremely fast and handles asynchronous operations perfectly, which we need when managing multiple laptops at once.

For the database, we are using SQLite in Write-Ahead Logging mode. We do not need a massive SQL server; this setup gives us database persistence and fast concurrent reads at zero cost and zero setup time.

For communication between the laptops, we are using gRPC for the heavy telemetry streaming, standard REST APIs for submitting tasks, and WebSockets to push live data to our frontend dashboard.

For the Machine Learning, we are using scikit-learn for the unsupervised monitoring models. For the reinforcement learning decision model, we will train it using PyTorch, but when we run it live, we will export it and run it using ONNX Runtime. This allows the AI to make decisions in under 5 milliseconds without needing an expensive graphics card.

For the frontend dashboard, we will use Next.js, along with charting libraries to build beautiful real-time graphs.

## 6. Detailed Explanation: Algorithms

Let me explain how the two AI models actually work without getting bogged down in math.

The first model is the Unsupervised Observer. Its job is to figure out if a laptop is safe to use. Every few seconds, it receives a snapshot of a laptop's hardware and mouse movements. It runs these numbers through two algorithms: DBSCAN and K-Means. DBSCAN removes any weird spikes in the data (like a sudden one-second CPU spike). Then, K-Means groups the clean data into three buckets. It learns to label these buckets as: "A human is typing", "The hardware is too busy doing something else", or "The machine is completely idle and safe to use". It does this automatically, adapting to each user's unique habits.

The second model is the Deep Q-Network Dispatcher. This is modeled like a video game. We are training it to play a game where it wins points for completing tasks, loses points if it uses dirty carbon energy, and loses massive points if it accidentally sends a task to a laptop while a human is typing on it. In production, this AI looks at the line of waiting tasks, checks the carbon forecast from WattTime, and decides which of the safe laptops should get the job.

## 7. Flow Diagrams Explained in Text

To help visualize how data moves through our system, here is how a typical task dispatch flows from start to finish.

Step 1: A big computing task is submitted to our central server.
Step 2: The server fetches the current carbon intensity data from the WattTime API.
Step 3: The server checks if the power grid is too dirty. If it is dirty, and there is no pressing emergency, it pauses and defers the task, waiting for the wind or solar energy to pick up.
Step 4: Once the grid is somewhat clean, the server asks the Observer AI: "Are any laptops currently in the safe idle state?"
Step 5: If laptops are safe to use, the server asks the Dispatcher AI to rank them and pick the absolute best one based on performance.
Step 6: The task is sent to the chosen worker laptop, and it begins computing in the background.
Step 7: Crucial step: while the task is running, if the human user comes back and bumps their mouse, the worker laptop immediately senses it and sends an emergency pause signal to the server. The task is frozen instantly to respect the user's priority.

## 8. Implementation Plan and Methodology

We will build GridMind in four distinct phases over roughly two months.

Phase 1 revolves around building the Foundation and Infrastructure. In this phase, we will set up the central FastAPI server and the SQLite database. We will also build the basic Python script that acts as the node agent to collect hardware data, and we will hook up our system to the WattTime API so we can start recording real carbon data.

Phase 2 focuses on the Observer AI Pipeline. We will set up the fast gRPC communication so the worker laptops can stream their data to the server. Then, we will write the DBSCAN and K-Means clustering logic. We will set up a background job so that this model automatically retrains itself every four hours to stay accurate.

Phase 3 is all about the Artificial Intelligence Dispatcher. Since this is Reinforcement Learning, we have to build a simulated environment first. We will train the model inside this simulation using historical carbon data until it learns how to optimally balance the penalties and rewards. Once it is smart enough, we will export it and plug it directly into our live FastAPI server.

Phase 4 is the Dashboard and Validation. We will build the Next.js frontend and hook up the WebSockets so we can watch our cluster operate in real-time. Finally, we will deploy the entire system across three of our actual laptops on a Wi-Fi network and run it for 24 hours to prove that it works exactly as designed.

## 9. Expected Outcomes

When we finish, we should hit some very specific numbers that prove our project is successful. 

First, when comparing our system to a regular task scheduler that just runs jobs immediately, our system must show at least a 20 percent reduction in carbon emissions.

Second, the system needs to be invisible to the user. We want a 90 percent success rate of tasks completing without having to be emergency-paused because a human came back to the keyboard.

Third, our Observer AI must achieve at least an 85 percent accuracy score when predicting if a machine is idle compared to human observation.

Finally, we want all of this to be incredibly fast. The server's AI decision to dispatch a task must take less than 10 milliseconds, and the tracking agent on the worker laptops should consume less than 2 percent of the CPU while it waits for jobs, ensuring we are not creating the very problem we are trying to solve.

I am excited to build this with you. Let's get started.
