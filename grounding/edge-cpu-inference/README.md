# Using edge devices for CPU-based inference

Machine learning models are most often trained in the “cloud”, on powerful centralized servers with specialized resources (like GPU acceleration) for training machine learning models.

However, for a variety of reasons including privacy, latency, and network connectivity or bandwidth constraints, it is often preferable to use these models (i.e. do inference) at “edge” devices located wherever the input data is/where the model’s prediction is going to be used.

These edge devices are less powerful and typically lack any special acceleration, so the inference time (the time from when the input is fed to the model, until the model outputs its prediction) may not be as fast as it would be on a cloud server - but we avoid having to send the input data to the cloud and then sending the prediction back.

In this experiment, we will use an edge device for inference in an image classification context.

To run this experiment on Chameleon, open a terminal inside the Chameleon Jupyter environment and run

```
cd ~/work
git clone https://github.com/teaching-on-testbeds/edge-cpu-inference
```

Then, open the notebook inside the `edge-cpu-inference` directory and follow along with the instructions there.

> Note: This experiment assumes that you already have a lease for an edge device on CHI@Edge!

---
This material is based upon work supported by the National Science Foundation under Grant No. 2230079.

