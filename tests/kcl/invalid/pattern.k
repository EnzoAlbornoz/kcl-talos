# Pattern checks run on evaluation.
# expect: url must satisfy: pattern
import talos.runtime as talos_runtime

d = talos_runtime.KmsgLogV1Alpha1 {url = "http://10.0.0.1:514"}
