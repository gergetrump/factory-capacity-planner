\ Model learning_inventory_limit
\ LP format - for model browsing. Use MPS format to capture full model detail.
Minimize
  B[T1] + B[T2]
Subject To
 useful_production: x[T1] + x[T2] <= 1
 capacity_T1: x[T1] - y[T1] <= 0
 nonempty_T1: - x[T1] + y[T1] <= 0
 staff_T1: y[T1] <= 1
 balance_T1: - x[T1] + I[T1] - B[T1] = 0
 inventory_sign_T1: I[T1] - sign[T1] <= 0
 backlog_sign_T1: B[T1] + sign[T1] <= 1
 capacity_T2: x[T2] <= 0
 nonempty_T2: - x[T2] + y[T2] <= 0
 staff_T2: y[T2] <= 1
 balance_T2: - x[T2] - I[T1] + I[T2] + B[T1] - B[T2] = -1
 inventory_sign_T2: I[T2] - sign[T2] <= 0
 backlog_sign_T2: B[T2] + sign[T2] <= 1
Bounds
\ Note: variable lower bounds are 0 unless specified otherwise
 x[T1] <= 1
 x[T2] = 0
 I[T1] <= 1
 I[T2] <= 1
 B[T1] = 0
 B[T2] <= 1
Binaries
 y[T1] y[T2] sign[T1] sign[T2]
Generals
 x[T1] x[T2] I[T1] I[T2] B[T1] B[T2]
End
