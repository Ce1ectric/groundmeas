# Project 
A python module to store measurement data from earthing measurements or earth fault tests within a database. Statistical analytics and plots and more are the main features of this module. 

# Feature Liste upcomming Versions
## rho-f model 
- calculation for a linear model Z(rho,f) = a * rho + b * f + c * rho * f
- function call groundmeas.analytics.rho_f_model(list_of_measurement_ids) -> {a:xx, b:xx, c:xx}, R^2 value
## Location all over the world
- change Location Model to add N,S or E,W for longitude and lattitude
