
# PlanAhead Launch Script for Post-Synthesis floorplanning, created by Project Navigator

create_project -name sintesi -dir "C:/Users/giulio/Desktop/sumavg/sintesi/planAhead_run_1" -part xc6slx45csg324-3
set_property design_mode GateLvl [get_property srcset [current_run -impl]]
set_property edif_top_file "C:/Users/giulio/Desktop/sumavg/sintesi/toplevel.ngc" [ get_property srcset [ current_run ] ]
add_files -norecurse { {C:/Users/giulio/Desktop/sumavg/sintesi} {../../sumavg2-main} }
set_param project.paUcfFile  "toplevel.ucf"
add_files "toplevel.ucf" -fileset [get_property constrset [current_run]]
open_netlist_design
