import React,{createRoot} from './react';
import {App} from './App';
class Boundary extends React.Component {
 state={error:null as Error|null};
 static getDerivedStateFromError(error:Error){return {error};}
 render(){if(this.state.error)return <main className="fatal-error"><h1>Your project couldn’t open.</h1><p>Your work is still saved on this computer. Refresh the app, or check the launch terminal if the problem continues.</p><button onClick={()=>location.reload()}>Refresh app</button></main>;return this.props.children;}
}
const root=document.getElementById('root');
if(!root)throw new Error('Storyboarder root element is missing.');
createRoot(root).render(<Boundary><App/></Boundary>);
